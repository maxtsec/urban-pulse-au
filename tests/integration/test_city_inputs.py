"""Real database import atomicity and fresh-process reconstruction."""

import copy
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update

from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.city_import import prepare_import
from urbanpulse.adapters.city_store import (
    CityInputStore,
    DomainExport,
    active_imports,
    encode,
    engine_for,
    imports,
    migrate,
    observations,
)
from urbanpulse.adapters.planning_fixture import FixturePlanningNormalizer
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.adapters.weather_fixture import FixtureWeatherNormalizer
from urbanpulse.application.capture_replay import payload_hash
from urbanpulse.application.city import CityService
from urbanpulse.application.composition import ComposedCityService
from urbanpulse.application.scenarios import Scenario

pytestmark = pytest.mark.integration
URL = os.environ.get(
    "URBANPULSE_TEST_DATABASE_URL",
    "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse",
)


@pytest.fixture
def stored(tmp_path):
    migrate(URL)
    engine = engine_for(URL)
    original = LocalCityCapture(tmp_path, capture_city(tmp_path)).read()
    captured = replace(original, capture_id=payload_hash([original.capture_id, uuid4().hex]))
    spatial = PostgisMembership(URL)
    rows = prepare_import(captured, spatial)
    store = CityInputStore(engine)
    scopes = []

    def save():
        scope = store.save(captured, rows)
        scopes.append(scope)
        return scope

    yield store, save, captured, rows, spatial
    with engine.begin() as connection:
        connection.execute(delete(imports).where(imports.c.id.in_(scopes)))
    engine.dispose()


@pytest.mark.parametrize("scenario", list(Scenario))
def test_persisted_export_matches_original_fixture_slices(stored, scenario):
    store, save, captured, rows, spatial = stored
    scope = save()
    inputs = store.load(scope)

    class Capture:
        def read(self):
            return captured

    direct = CityService(
        Capture(), spatial, FixtureWeatherNormalizer(), FixturePlanningNormalizer()
    )
    recovered = CityService(inputs, spatial, inputs=inputs)
    for seconds in (0, 60, 120, 150, 180, 240, 270, 360):
        assert json.loads(encode(recovered.snapshot(seconds, scenario))) == json.loads(
            encode(direct.snapshot(seconds, scenario))
        )
        assert json.loads(
            encode(recovered.evidence(captured.capture_id, seconds, scenario))
        ) == json.loads(encode(direct.evidence(captured.capture_id, seconds, scenario)))


def test_idempotent_concurrent_imports_and_original_trace_context(stored):
    store, save, captured, rows, spatial = stored
    with ThreadPoolExecutor(max_workers=2) as pool:
        scopes = list(pool.map(lambda _: save(), range(2)))
    assert scopes[0] == scopes[1]
    inputs = store.load(scopes[0])
    assert (
        inputs.captured.scenario["frames"][4]["event"]["traceparent"]
        == captured.scenario["frames"][4]["event"]["traceparent"]
    )
    with store.engine.connect() as connection:
        count = connection.execute(
            select(func.count()).select_from(imports).where(imports.c.id == scopes[0])
        ).scalar_one()
        assert count == 1
    modified = copy.deepcopy(rows)
    modified["weather"][0]["evidence"]["id"] = "changed"
    with pytest.raises(ValueError, match="differs"):
        store.save(captured, modified)


def test_partial_import_rolls_back_every_owner(stored, monkeypatch):
    store, save, captured, rows, spatial = stored
    original = DomainExport.write

    def fail(self, connection, scope, values):
        original(self, connection, scope, values)
        if self.owner == "weather":
            raise RuntimeError("interrupted import")

    with monkeypatch.context() as patch:
        patch.setattr(DomainExport, "write", fail)
        with pytest.raises(RuntimeError, match="interrupted"):
            save()
    with store.engine.connect() as connection:
        assert (
            connection.execute(
                select(func.count())
                .select_from(imports)
                .where(imports.c.capture_id == captured.capture_id)
            ).scalar_one()
            == 0
        )
    scope = save()
    assert store.load(scope).captured.capture_id == captured.capture_id


def test_fresh_process_recovers_after_commit_without_raw_files_or_normalizers(stored):
    store, save, captured, rows, spatial = stored
    scope = save()  # Deliberately no dispatch before starting a different process.
    inputs = store.load(scope)
    expected = ComposedCityService(CityService(inputs, spatial, inputs=inputs), inputs).snapshot(
        240, "weather-outage"
    )
    code = """
import os,sys,hashlib
from pathlib import Path
from urbanpulse.adapters.city_store import CityInputStore,engine_for,encode
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.adapters.weather_fixture import FixtureWeatherNormalizer
from urbanpulse.adapters.planning_fixture import FixturePlanningNormalizer
from urbanpulse.application.city import CityService
from urbanpulse.application.composition import ComposedCityService

def forbidden(*args,**kwargs):raise AssertionError('raw fixture/normalizer used during recovery')
Path.read_bytes=forbidden
FixtureWeatherNormalizer.warning=forbidden
FixtureWeatherNormalizer.reading=forbidden
FixturePlanningNormalizer.snapshot=forbidden
url=os.environ['URBANPULSE_TEST_DATABASE_URL']
engine=engine_for(url)
inputs=CityInputStore(engine).load(sys.argv[1])
view=ComposedCityService(CityService(inputs,PostgisMembership(url),inputs=inputs),inputs).snapshot(240,'weather-outage')
print(hashlib.sha256(encode(view).encode()).hexdigest())
engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, scope],
        env={**os.environ, "URBANPULSE_TEST_DATABASE_URL": URL},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    import hashlib

    assert result.stdout.strip() == hashlib.sha256(encode(expected).encode()).hexdigest()


def test_corrupt_observation_is_rejected_not_silently_served(stored):
    store, save, captured, rows, spatial = stored
    scope = save()
    table = observations["weather"]
    with store.engine.begin() as connection:
        row = (
            connection.execute(
                select(table.c.body).where(table.c.scope == scope).order_by(table.c.sequence)
            )
            .scalars()
            .first()
        )
        body = json.loads(row)
        body["evidence"]["id"] = "tampered"
        connection.execute(
            update(table)
            .where(table.c.scope == scope, table.c.sequence == 0)
            .values(body=encode(body))
        )
    with pytest.raises(ValueError, match="integrity"):
        store.load(scope)


def test_missing_import_is_unavailable(stored):
    store, *_ = stored
    with pytest.raises(ValueError, match="inputs missing"):
        store.load("0" * 64)


def test_explicit_selection_survives_reimport_and_failed_import(stored, monkeypatch):
    store, save, captured, rows, spatial = stored
    name = "test-" + uuid4().hex
    scope = save()
    try:
        with pytest.raises(ValueError, match="not selected"):
            store.active_scope(name)
        assert store.save(captured, rows, activate=name) == scope
        assert CityInputStore(store.engine).active_scope(name) == scope
        assert store.save(captured, rows, activate=name) == scope
        different = replace(captured, capture_id=payload_hash([captured.capture_id, "interrupted"]))
        original = DomainExport.write

        def fail(self, connection, new_scope, values):
            original(self, connection, new_scope, values)
            if self.owner == "weather":
                raise RuntimeError("interrupted selection")

        with monkeypatch.context() as patch:
            patch.setattr(DomainExport, "write", fail)
            with pytest.raises(RuntimeError):
                store.save(different, rows, activate=name)
        assert store.active_scope(name) == scope
        inputs = CityInputStore(store.engine).load(store.active_scope(name))
        assert inputs.captured.capture_id == captured.capture_id
    finally:
        with store.engine.begin() as connection:
            connection.execute(delete(active_imports).where(active_imports.c.name == name))


def test_unselected_import_cannot_change_active_city(stored):
    store, save, captured, rows, spatial = stored
    name = "test-" + uuid4().hex
    scope = save()
    other_scope = None
    try:
        store.save(captured, rows, activate=name)
        other = replace(captured, capture_id=payload_hash([captured.capture_id, "other"]))
        other_scope = store.save(other, rows)
        assert other_scope != scope
        assert store.active_scope(name) == scope
        store.save(other, rows, activate=name)
        assert store.active_scope(name) == other_scope
        store.save(captured, rows, activate=name)
        assert store.active_scope(name) == scope
    finally:
        with store.engine.begin() as connection:
            connection.execute(delete(active_imports).where(active_imports.c.name == name))
            if other_scope:
                connection.execute(delete(imports).where(imports.c.id == other_scope))


def test_api_reuses_spatial_cache_but_still_loads_inputs_per_request(stored, monkeypatch):
    from types import SimpleNamespace

    from apps.api.city import city_service, spatial_membership

    store, save, captured, rows, spatial = stored
    scope = save()
    queries = {"covers": 0, "overlap": 0, "loads": 0}
    covers = PostgisMembership._query_covers
    overlaps = PostgisMembership._query_overlap

    def query_covers(self, *args):
        queries["covers"] += 1
        return covers(self, *args)

    def query_overlap(self, *args):
        queries["overlap"] += 1
        return overlaps(self, *args)

    def load(selected):
        queries["loads"] += 1
        return store.load(selected)

    monkeypatch.setattr(PostgisMembership, "_query_covers", query_covers)
    monkeypatch.setattr(PostgisMembership, "_query_overlap", query_overlap)
    monkeypatch.setattr(
        "apps.api.city.input_store", lambda: SimpleNamespace(active_scope=lambda: scope, load=load)
    )
    monkeypatch.setattr("apps.api.city.Settings", lambda: SimpleNamespace(database_url=URL))
    spatial_membership.cache_clear()
    try:
        first = city_service().snapshot(180, "city")
        spatial_counts = (queries["covers"], queries["overlap"])
        assert all(spatial_counts)
        assert city_service().snapshot(180, "city") == first
        assert (queries["covers"], queries["overlap"]) == spatial_counts
        assert queries["loads"] == 2
    finally:
        spatial_membership.cache_clear()
