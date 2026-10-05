"""Rehearse the compiled frontend against an isolated Redis-free fixture API."""

import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from uuid import uuid4

from scripts.compose_smoke import ROOT, cleanup_stack, project_volumes


def check_response(base: str, path: str, expected: int = 200) -> object:
    try:
        with urllib.request.urlopen(base + path, timeout=15) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    if status != expected:
        raise RuntimeError(f"{path}: expected HTTP {expected}, received {status}")
    if expected >= 400 and b'<div id="root">' in body:
        raise RuntimeError(f"{path}: error was replaced by the SPA")
    try:
        return json.loads(body)
    except ValueError:
        return body.decode()


def main() -> None:
    project = "urbanpulse-smoke-" + uuid4().hex[:12]
    folder = ROOT / ".local" / "web-serving-smoke" / project
    folder.mkdir(parents=True)
    log_path = folder / "docker.log"
    base = ["docker", "compose", "--project-name", project]
    for file in (
        "compose.yaml",
        "compose.no-cache.yaml",
        "compose.serving.yaml",
        "scripts/web-serving-smoke.override.yaml",
    ):
        base.extend(["-f", str(ROOT / file)])
    base.extend(["--profile", "app"])
    known_volumes: set[str] = set()
    with log_path.open("w", encoding="utf-8") as log:

        def run(*args: str, all_profiles: bool = False, capture: bool = False) -> str:
            if args[0] in {"up", "rm"}:
                known_volumes.update(project_volumes(project))
            command = [*base]
            if all_profiles:
                command.extend(["--profile", "*"])
            result = subprocess.run(
                [*command, *args],
                cwd=ROOT,
                text=True,
                timeout=900,
                stdout=subprocess.PIPE if capture else log,
                stderr=log,
            )
            log.flush()
            if result.returncode:
                raise RuntimeError(f"Compose {' '.join(args)} failed; inspect {log_path}")
            return result.stdout if capture else ""

        try:
            print(f"Building compiled serving rehearsal: {project}", flush=True)
            run("build", "api", "web")
            run("up", "-d", "--wait")
            origin = "http://" + run("port", "web", "8088", capture=True).strip()
            healthy = check_response(origin, "/health/ready")
            if not isinstance(healthy, dict) or healthy.get("redis") != "disabled":
                raise RuntimeError("serving rehearsal must use Redis-free readiness")
            if run("ps", "--all", "--quiet", "redis", capture=True).strip():
                raise RuntimeError("Redis unexpectedly present in serving rehearsal")
            if run("exec", "-T", "web", "id", "-u", capture=True).strip() != "10001":
                raise RuntimeError("web runtime must be non-root")
            run(
                "exec",
                "-T",
                "web",
                "sh",
                "-ec",
                "test ! -d /app/node_modules; test ! -d /app/src; "
                "test ! -f /srv/package.json; ! command -v node",
            )
            print(f"Checking compiled city in Chromium: {origin}", flush=True)
            npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
            if npm is None:
                raise RuntimeError("npm is required for the serving browser checks")
            subprocess.run(
                [
                    npm,
                    "exec",
                    "--",
                    "playwright",
                    "test",
                    "--config",
                    "playwright.serving.config.ts",
                ],
                cwd=ROOT / "apps/web",
                check=True,
                timeout=900,
                env={**os.environ, "URBANPULSE_SERVING_URL": origin},
            )
            route = "/api/v1/areas/au-vic-melbourne-clue-southbank?scenario=city&seconds=180"
            expected = check_response(origin, route)
            print("Checking API/database outage and recovery through Caddy", flush=True)
            run("stop", "api")
            check_response(origin, "/")
            check_response(origin, "/health/live", 502)
            check_response(origin, "/health/ready", 502)
            check_response(origin, route, 502)
            run("up", "-d", "--no-deps", "--wait", "api")
            if check_response(origin, route) != expected:
                raise RuntimeError("city changed after API recovery")
            run("stop", "postgres")
            check_response(origin, "/")
            check_response(origin, "/health/live")
            check_response(origin, "/health/ready", 503)
            check_response(origin, route, 503)
            run("up", "-d", "--wait", "postgres")
            check_response(origin, "/health/ready")
            if check_response(origin, route) != expected:
                raise RuntimeError("city changed after database recovery")
            print("Compiled serving, browser flows and outage/recovery checks passed", flush=True)
        finally:
            primary_error = sys.exception()
            if primary_error is not None:
                try:
                    run("logs", "--no-color")
                except Exception as log_error:
                    primary_error.add_note(f"Container logs unavailable: {log_error}")
            try:
                cleanup_stack(project, run, known_volumes)
            except Exception as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(f"Cleanup also failed: {cleanup_error}")
                print(f"Cleanup failed; inspect {log_path}", file=sys.stderr)
            else:
                print(
                    f"Verified containers, networks and recorded volumes removed; log: {log_path}"
                )


if __name__ == "__main__":
    main()
