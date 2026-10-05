"""Build and test the app profile on isolated volumes/ports, then remove only that stack."""

import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def require_equal(actual: object, expected: object, context: str) -> None:
    if actual != expected:
        raise RuntimeError(f"{context}: city response changed")


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

    with log_path.open("w", encoding="utf-8") as log:

        def run(*args: str) -> None:
            result = subprocess.run(
                [*base, *args], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=900
            )
            log.flush()
            if result.returncode:
                raise RuntimeError(f"Compose {' '.join(args)} failed; inspect {log_path}")

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
            print(
                "Compose smoke passed: cold readiness, initializer, city/boundary/evidence, "
                "proxy and recreation",
                flush=True,
            )
        finally:
            primary_error = sys.exception()
            try:
                # Never target the user's normal compose project or its database volume.
                if not re.fullmatch(r"urbanpulse-smoke-[0-9a-f]{12}", project):
                    raise RuntimeError("invalid isolated cleanup target")
                run("down", "--volumes", "--remove-orphans")
            except Exception as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(f"Cleanup also failed: {cleanup_error}")
                print(f"Cleanup failed for {project}; inspect {log_path}", file=sys.stderr)
            else:
                print(f"Removed isolated stack; log: {log_path}", flush=True)


if __name__ == "__main__":
    main()
