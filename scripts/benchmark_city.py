"""Measure replay cost without changing application state or production behavior."""

import argparse
import gc
import hashlib
import json
import platform
import subprocess
import sys
import warnings
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import make_url, text

from scripts.benchmark_workload import WORKLOAD_VERSION, planning_history
from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.city_import import prepare_import
from urbanpulse.adapters.city_store import CityInputStore, encode, engine_for, migrate
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.application.city import CapturedCity, CityService
from urbanpulse.application.composition import ComposedCityService, transition_clocks
from urbanpulse.config import Settings
from urbanpulse.location.planning import PlanningProjection


@contextmanager
def isolated_store(database_url: str) -> Iterator[CityInputStore]:
    """Create and remove only this invocation's fresh, randomly named schema."""
    schema = "urbanpulse_bench_" + uuid4().hex
    admin = engine_for(database_url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        url = make_url(database_url).update_query_dict({"options": f"-csearch_path={schema}"})
        private_url = url.render_as_string(hide_password=False)
        migrate(private_url)
        engine = engine_for(private_url)
        yield CityInputStore(engine)
    finally:
        failed = sys.exc_info()[0] is not None
        if engine is not None:
            engine.dispose()
        try:
            if created:
                with admin.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        except Exception:
            if not failed:
                raise
            warnings.warn(
                "Benchmark schema cleanup also failed; original error retained", stacklevel=2
            )
        finally:
            admin.dispose()


def fingerprint(value: Any) -> str:
    return hashlib.sha256(encode(value).encode()).hexdigest()


def measure(operation: Callable[[], Any], repeats: int) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("at least one measured repetition is required")
    expected = fingerprint(operation())  # warmup; checking output is outside the timer
    samples = []
    for _ in range(repeats):
        gc.collect()
        start = perf_counter()
        result = operation()
        elapsed = perf_counter() - start
        if fingerprint(result) != expected:
            raise ValueError("benchmark result changed between repetitions")
        samples.append(elapsed * 1000)
    return {
        "samples_ms": samples,
        "median_ms": median(samples),
        "min_ms": min(samples),
        "max_ms": max(samples),
        "result_sha256": expected,
    }


def profile_copies(operation: Callable[[], Any], expected: str) -> dict[str, Any]:
    """Separate instrumented pass; wrapper overhead is excluded from normal timings."""
    totals = {"calls": 0, "seconds": 0.0, "planning_calls": 0, "planning_seconds": 0.0}

    def timed_copy(value: Any) -> Any:
        start = perf_counter()
        result = deepcopy(value)
        elapsed = perf_counter() - start
        totals["calls"] += 1
        totals["seconds"] += elapsed
        if isinstance(value, PlanningProjection):
            totals["planning_calls"] += 1
            totals["planning_seconds"] += elapsed
        return result

    with patch("urbanpulse.application.delivery.deepcopy", timed_copy):
        start = perf_counter()
        result = operation()
        elapsed = perf_counter() - start
    if fingerprint(result) != expected:
        raise ValueError("instrumented replay differs from uninstrumented replay")
    return {**totals, "instrumented_seconds": elapsed}


def benchmark_case(
    store: CityInputStore,
    base: CapturedCity,
    spatial: PostgisMembership,
    snapshots: int,
    records: int,
    repeats: int,
) -> dict[str, Any]:
    captured = planning_history(base, snapshots, records)
    scope = store.save(captured, prepare_import(captured, spatial))  # never activate this import
    inputs = store.load(scope)
    if len(inputs.planning) != snapshots or any(step.event is None for step in inputs.planning):
        raise ValueError("benchmark planning inputs were not fully accepted")

    def single() -> dict[str, Any]:
        return CityService(inputs, spatial, inputs=inputs).snapshot(360, "city")

    def composed() -> dict[str, Any]:
        city = CityService(inputs, spatial, inputs=inputs)
        return ComposedCityService(city, inputs).snapshot(360, "city")

    planning = single()["planning"]
    if (
        len(planning["snapshots"]) != snapshots
        or len(planning["records"]) != records
        or planning["projection"]["apply"] != snapshots
        or planning["state"] != "current"
    ):
        raise ValueError("benchmark replay omitted expected planning history or records")
    load = measure(lambda: store.load(scope), repeats)
    one = measure(single, repeats)
    replay = measure(composed, repeats)
    return {
        "snapshots": snapshots,
        "records_per_snapshot": records,
        "transition_clocks": len(transition_clocks(inputs, 360)),
        "capture_sha256": captured.capture_id,
        "load": load,
        "single_snapshot": one,
        "composed_replay": replay,
        "copy_profile": profile_copies(composed, replay["result_sha256"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--histories", nargs="+", type=int, default=[1, 10, 30])
    parser.add_argument("--records", nargs="+", type=int, default=[10, 100])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path(".local/benchmarks/city.json"))
    args = parser.parse_args()
    if (
        args.repeats < 1
        or args.repeats > 20
        or any(not 1 <= value <= 60 for value in args.histories)
        or any(not 1 <= value <= 1000 for value in args.records)
    ):
        parser.error("histories: 1..60; records: 1..1000; repeats: 1..20")
    settings = Settings()
    capture_path = Path(".local/benchmarks/raw")
    base = LocalCityCapture(capture_path, capture_city(capture_path)).read()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report = {
        "workload_version": WORKLOAD_VERSION,
        "benchmark_source_sha256": {
            name: hashlib.sha256(Path("scripts", name).read_bytes()).hexdigest()
            for name in ("benchmark_city.py", "benchmark_workload.py")
        },
        "revision": revision,
        "measured_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.system(),
        "repeats": args.repeats,
        "clock_seconds": 360,
        "conditions": "local PostGIS; warm spatial cache; sequential; no HTTP",
        "cases": [],
    }
    with isolated_store(settings.database_url) as store:
        for records in args.records:
            for snapshots in args.histories:
                case = benchmark_case(
                    store,
                    base,
                    PostgisMembership(settings.database_url),
                    snapshots,
                    records,
                    args.repeats,
                )
                report["cases"].append(case)
                print(f"Measured {snapshots} snapshots x {records} records", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Benchmark report saved; temporary database schema removed")


if __name__ == "__main__":
    main()
