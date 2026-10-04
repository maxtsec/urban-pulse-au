"""Start temporary API/Vite servers, verify their connection, then stop them."""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.read()


def wait_for(url: str, process: subprocess.Popen[bytes]) -> bytes:
    for _ in range(45):
        if process.poll() is not None:
            raise RuntimeError(f"Server exited before {url}; see .local/smoke logs")
        try:
            return fetch(url)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}")


def main() -> None:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is not on PATH; reopen your terminal after installation")
    log_dir = ROOT / ".local/smoke"
    log_dir.mkdir(parents=True, exist_ok=True)
    processes: list[subprocess.Popen[bytes]] = []
    with (log_dir / "api.log").open("wb") as api_log, (log_dir / "web.log").open("wb") as web_log:
        try:
            api = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "apps.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                cwd=ROOT,
                stdout=api_log,
                stderr=subprocess.STDOUT,
            )
            processes.append(api)
            live = json.loads(wait_for("http://127.0.0.1:8000/health/live", api))
            assert live["mode"] == "fixture"
            web_env = dict(os.environ, VITE_API_PROXY="http://127.0.0.1:8000")
            web = subprocess.Popen(
                [node, "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "5173"],
                cwd=ROOT / "apps/web",
                env=web_env,
                stdout=web_log,
                stderr=subprocess.STDOUT,
            )
            processes.append(web)
            html = wait_for("http://127.0.0.1:5173", web)
            assert b"UrbanPulse" in html
            fixture = json.loads(fetch("http://127.0.0.1:5173/api/v1/fixture"))
            assert fixture["mode"] == "fixture"
            assert len(fixture["observations"]) == 3
            assert fixture["observations"][1]["delay_seconds"] is None
            print("PASS: HTTP API, Vite page and Vite -> FastAPI proxy with synthetic fixture")
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
