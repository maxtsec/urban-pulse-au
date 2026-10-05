"""Build and test the app profile on isolated volumes/ports, then remove only that stack."""

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def require_equal(actual: object, expected: object, context: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{context}: city response changed")


def verify_database_restart(
    base: list[str],
    run: Callable[..., None],
    recovery: Callable[..., object],
) -> None:
    """Restart only the generated smoke project's database and keep its worker alive."""
    run("up", "-d", "--no-deps", "recovery-worker")
    container = subprocess.check_output(
        [*base, "ps", "-q", "recovery-worker"], cwd=ROOT, text=True
    ).strip()

    def incarnation() -> str:
        return subprocess.check_output(
            ["docker", "inspect", "--format", "{{.State.StartedAt}} {{.RestartCount}}", container],
            cwd=ROOT,
            text=True,
        ).strip()

    before = incarnation()
    run("stop", "postgres")
    deadline = time.monotonic() + 30
    while True:
        logs = subprocess.check_output(
            [*base, "logs", "--no-color", "recovery-worker"],
            cwd=ROOT,
            text=True,
        )
        if '"error": "database-unavailable"' in logs:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("worker did not report the database outage")
        time.sleep(0.25)
    run("up", "-d", "--wait", "postgres")
    recovery("seed-probe", "--context", "compose-after-db-restart")
    deadline = time.monotonic() + 75
    while True:
        rows = recovery("list", "--context", "compose-after-db-restart")
        if isinstance(rows, list) and rows and rows[0].get("status") == "complete":
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("worker did not resume after database restart")
        time.sleep(0.5)
    require_equal(incarnation(), before, "Worker survived database restart")
    run("stop", "recovery-worker")


def verify_city_checkpoints(run, city, read, api):
    """Advance explicitly, then recreate the worker across persisted warning expiry."""
    route = api + "/api/v1/areas/au-vic-melbourne-clue-southbank"

    def completed(run_id, seconds, scenario):
        deadline = time.monotonic() + 90
        while True:
            value = city("inspect", run_id)
            if value["completed"] == seconds:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("city worker did not complete its checkpoint")
            time.sleep(0.5)
        expected = read(route + f"?scenario={scenario}&seconds={seconds}")
        actual = value["snapshot"]
        for view in (expected, actual):
            view["composition"].pop("delivery", None)
            view["composition"].pop("recovery", None)
        require_equal(actual, expected, "Durable city checkpoint")
        return value

    city("create", "compose-city", "--scenario", "city")
    city("advance", "compose-city", "--seconds", "60")
    run("up", "-d", "--no-deps", "city-worker")
    completed("compose-city", 60, "city")
    city("create", "compose-expiry", "--scenario", "weather-outage")
    city("advance", "compose-expiry", "--seconds", "239")
    completed("compose-expiry", 239, "weather-outage")
    run("stop", "city-worker")
    city("advance", "compose-expiry", "--seconds", "240")
    before = city("inspect", "compose-expiry")
    require_equal(before["completed"], 239, "Stopped city worker")
    read(route + "?scenario=city&seconds=360")
    require_equal(city("inspect", "compose-expiry"), before, "Read-only browser clock")
    run("up", "-d", "--no-deps", "--force-recreate", "city-worker")
    after = completed("compose-expiry", 240, "weather-outage")
    require_equal(after["snapshot"]["assessment"]["condition"], "unknown", "Warning expiry")
    run("stop", "city-worker")


def verify_cache_modes(base, run, read, url, route, view):
    """Exercise enabled failure, a Redis-free app graph, and database failure/recovery."""
    healthy = {"status": "ok", "postgis": "ok", "redis": "ok", "mode": "fixture"}
    disabled = {**healthy, "redis": "disabled"}
    require_equal(read(url("api", 8000) + "/health/ready"), healthy, "Enabled cache")
    run("stop", "redis")
    read(url("api", 8000) + "/health/ready", 503)
    require_equal(read(url("api", 8000) + route), view, "City during cache outage")
    run("rm", "-f", "-v", "redis")
    run("up", "-d", "--wait", no_cache=True)
    containers = subprocess.check_output(
        [*base, "ps", "--all", "--quiet", "redis"], cwd=ROOT, text=True
    ).strip()
    require_equal(containers, "", "Redis-free Compose graph")
    api = url("api", 8000)
    require_equal(read(api + "/health/ready"), disabled, "Disabled cache")
    require_equal(read(api + route), view, "Redis-free city")
    run("stop", "postgres", no_cache=True)
    read(api + "/health/ready", 503)
    read(api + route, 503)
    read(api + "/health/live")
    run("up", "-d", "--wait", "postgres", no_cache=True)
    require_equal(read(api + "/health/ready"), disabled, "Redis-free database recovery")
    require_equal(read(api + route), view, "Redis-free city recovery")
    run("up", "-d", "--wait", "api")
    api = url("api", 8000)
    require_equal(read(api + "/health/ready"), healthy, "Re-enabled cache")
    require_equal(read(api + route), view, "City after re-enabling cache")


def project_volumes(project: str) -> set[str]:
    """Remember volume mounts while their owning project containers still exist."""
    if not re.fullmatch(r"urbanpulse-smoke-[0-9a-f]{12}", project):
        raise RuntimeError("invalid isolated cleanup target")
    containers = subprocess.check_output(
        [
            "docker",
            "container",
            "ls",
            "--quiet",
            "--all",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        cwd=ROOT,
        text=True,
        timeout=30,
    ).splitlines()
    volumes: set[str] = set()
    for container in containers:
        # Inspect mounts only: full inspection would include environment credentials.
        mounts = json.loads(
            subprocess.check_output(
                ["docker", "container", "inspect", "--format", "{{json .Mounts}}", container],
                cwd=ROOT,
                text=True,
                timeout=30,
            )
        )
        volumes.update(mount["Name"] for mount in mounts if mount["Type"] == "volume")
    return volumes


def cleanup_stack(
    project: str, run: Callable[..., None], known_volumes: set[str] | None = None
) -> None:
    """Remove every profile, checking labels and mounts recorded before container removal."""
    if not re.fullmatch(r"urbanpulse-smoke-[0-9a-f]{12}", project):
        raise RuntimeError("invalid isolated cleanup target")
    volumes = set(known_volumes or ())
    inventory_error = None
    try:
        volumes.update(project_volumes(project))
    except Exception as error:
        inventory_error = error
    # Still attempt teardown if Docker could not provide the mount inventory.
    try:
        run("down", "--volumes", "--remove-orphans", all_profiles=True)
    except Exception as error:
        if inventory_error is not None:
            error.add_note(f"Volume inventory also failed: {inventory_error}")
        raise
    if inventory_error is not None:
        raise RuntimeError("Cannot verify cleanup: volume inventory failed") from inventory_error
    remaining: dict[str, list[str]] = {}
    for resource in ("container", "network", "volume"):
        command = ["docker", resource, "ls", "--quiet"]
        if resource == "container":
            command.append("--all")
        command.extend(["--filter", f"label=com.docker.compose.project={project}"])
        identifiers = subprocess.check_output(command, cwd=ROOT, text=True, timeout=30).splitlines()
        if identifiers:
            remaining[resource] = identifiers
    if volumes:
        existing = set(
            subprocess.check_output(
                ["docker", "volume", "ls", "--quiet"],
                cwd=ROOT,
                text=True,
                timeout=30,
            ).splitlines()
        )
        surviving = sorted(volumes & existing)
        if surviving:
            remaining["recorded volume mounts"] = surviving
    if remaining:
        raise RuntimeError(f"Smoke cleanup left resources: {remaining}")


def main() -> None:
    project = "urbanpulse-smoke-" + uuid4().hex[:12]
    folder = ROOT / ".local" / "compose-smoke" / project
    folder.mkdir(parents=True)
    log_path = folder / "docker.log"
    base = [
        "docker",
        "compose",
        "--project-name",
        project,
        "-f",
        str(ROOT / "compose.yaml"),
        "-f",
        str(ROOT / "scripts/compose-smoke.override.yaml"),
        "--profile",
        "app",
    ]

    known_volumes: set[str] = set()
    with log_path.open("w", encoding="utf-8") as log:

        def run(*args: str, no_cache: bool = False, all_profiles: bool = False) -> None:
            # Up may recreate a container; rm removes its ownership evidence outright.
            if args[0] in {"up", "rm"}:
                known_volumes.update(project_volumes(project))
            configuration = [*base]
            if no_cache:
                configuration.extend(["-f", str(ROOT / "compose.no-cache.yaml")])
            if all_profiles:
                configuration.extend(["--profile", "*"])
            result = subprocess.run(
                [*configuration, *args], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=900
            )
            log.flush()
            if result.returncode:
                raise RuntimeError(f"Compose {' '.join(args)} failed; inspect {log_path}")

        def command(service: str, module: str, *args: str) -> object:
            result = subprocess.run(
                [
                    *base,
                    "run",
                    "--rm",
                    "--no-deps",
                    service,
                    "/app/.venv/bin/python",
                    "-m",
                    module,
                    *args,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
            log.write(result.stdout + result.stderr)
            log.flush()
            if result.returncode:
                raise RuntimeError(f"Recovery worker failed; inspect {log_path}")
            return json.loads(result.stdout)

        def recovery(*args: str) -> object:
            return command("recovery-worker", "workers.events.main", *args)

        def city(*args: str) -> object:
            return command("city-worker", "workers.city.main", *args)

        def url(service: str, port: int) -> str:
            address = subprocess.check_output(
                [*base, "port", service, str(port)], cwd=ROOT, text=True
            ).strip()
            return f"http://{address}"

        def read(endpoint: str, expected: int = 200) -> object:
            try:
                with urllib.request.urlopen(endpoint, timeout=30) as response:
                    status, body = response.status, response.read()
            except urllib.error.HTTPError as error:
                status, body = error.code, error.read()
            if status != expected:
                raise AssertionError(f"{endpoint} returned {status}, expected {expected}")
            try:
                return json.loads(body)
            except ValueError:
                return body.decode()

        try:
            print(f"Building isolated app images: {project}", flush=True)
            run("build", "api", "web")
            run("up", "-d", "--wait", "postgres", "redis")
            print("Checking basic readiness before migrations/import", flush=True)
            run("up", "-d", "--no-deps", "--wait", "api")
            api = url("api", 8000)
            read(api + "/health/ready")
            read(api + "/api/v1/fixture")
            read(
                api + "/api/v1/areas/au-vic-melbourne-clue-southbank?scenario=city&seconds=360", 503
            )
            print("Starting full app profile with one-shot city initialization", flush=True)
            run("up", "-d", "--wait")
            api = url("api", 8000)
            route = "/api/v1/areas/au-vic-melbourne-clue-southbank?scenario=city&seconds=360"
            view = read(api + route)
            if not isinstance(view, dict):
                raise RuntimeError("city response must be an object")
            if view.get("composition", {}).get("recovery") != "persisted-domain-inputs":
                raise RuntimeError("city response must use persisted domain inputs")
            read(api + view["geometry_url"])
            read(api + view["evidence_url"])
            require_equal(read(url("web", 5173) + route), view, "UI proxy")
            print("Recreating API without sharing initializer files", flush=True)
            run("up", "-d", "--no-deps", "--force-recreate", "--wait", "api")
            api = url("api", 8000)
            require_equal(read(api + route), view, "API recreation")
            print("Repeating initialization against existing inputs", flush=True)
            run("run", "--rm", "city-init")
            require_equal(read(api + route), view, "Repeated initialization")
            print("Checking independent recovery worker and replay", flush=True)
            recovery("seed-probe", "--context", "compose-recovery")
            processed = recovery("run", "--once")
            if not isinstance(processed, dict):
                raise RuntimeError("recovery worker must return a result")
            require_equal(processed["status"], "apply", "Initial recovery effect")
            recovery(
                "replay",
                processed["delivery_id"],
                "--generation",
                str(processed["generation"]),
                "--reason",
                "verify-deduplication",
            )
            repeated = recovery("run", "--once")
            if not isinstance(repeated, dict):
                raise RuntimeError("recovery replay must return a result")
            require_equal(repeated["status"], "duplicate", "Recovery replay")
            require_equal(read(api + route), view, "Recovery worker isolation")
            print("Checking durable city checkpoints and persisted expiry", flush=True)
            verify_city_checkpoints(run, city, read, api)
            metrics = city("metrics")
            if not isinstance(metrics, dict) or not isinstance(metrics.get("consumers"), list):
                raise RuntimeError("city metrics must return registered consumer summaries")
            require_equal(
                sorted(item["consumer"] for item in metrics["consumers"]),
                ["city-location-v1", "city-results-v1"],
                "City operational metrics",
            )
            print("Restarting isolated database while worker stays running", flush=True)
            verify_database_restart(base, run, recovery)
            require_equal(read(api + route), view, "Database restart isolation")
            print(
                "Checking enabled, absent and re-enabled Redis with database recovery", flush=True
            )
            verify_cache_modes(base, run, read, url, route, view)
            print(
                "Compose smoke passed: cold readiness, initializer, city/boundary/evidence, "
                "proxy, recreation, city checkpoints/expiry, worker replay "
                "and database restart recovery, optional cache modes",
                flush=True,
            )
        finally:
            primary_error = sys.exception()
            try:
                # Never target the user's normal compose project or its database volume.
                cleanup_stack(project, run, known_volumes)
            except Exception as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(f"Cleanup also failed: {cleanup_error}")
                print(f"Cleanup failed for {project}; inspect {log_path}", file=sys.stderr)
            else:
                print(
                    "Verified no project-labelled resources or recorded volume mounts remain; "
                    f"log: {log_path}",
                    flush=True,
                )


if __name__ == "__main__":
    main()
