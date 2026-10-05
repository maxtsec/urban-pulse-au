"""Build static assets and prove fake local secrets are excluded from the web context."""

import json
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    identity = uuid4().hex
    workspace = (ROOT / ".local" / "web-build-smoke" / identity).resolve()
    if not workspace.is_relative_to(ROOT):
        raise RuntimeError("smoke output must remain inside the repository")
    context = workspace / "context"
    context.mkdir(parents=True)
    # Copy tracked paths only; private workstation files must never enter the probe context.
    tracked = (
        subprocess.check_output(["git", "ls-files", "-z", "apps/web"], cwd=ROOT)
        .decode()
        .split("\0")
    )
    for name in filter(None, tracked):
        source = ROOT / name
        relative = source.relative_to(ROOT / "apps" / "web")
        if not source.resolve().is_relative_to(ROOT / "apps" / "web"):
            raise RuntimeError("web source must remain inside its build context")
        destination = context / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    probes = [
        ".env",
        ".env.production",
        ".npmrc",
        "private.key",
        "certificate.pem",
        "AGENTS.md",
        "CLAUDE.md",
        "agent.md",
        "claude.md",
        ".local/probe",
        ".git/probe",
        "nested/.env.local",
        "nested/AGENTS.md",
        "nested/private.key",
    ]
    for name in probes:
        path = context / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SYNTHETIC_BUILD_CONTEXT_PROBE", encoding="utf-8")
    image = "urbanpulse-web-build-smoke:" + identity
    log_path = workspace / "docker.log"
    try:
        with log_path.open("w", encoding="utf-8") as log:

            def run(*args: str) -> None:
                subprocess.run(["docker", *args], cwd=ROOT, stdout=log, stderr=log, check=True)

            run("build", "--target", "build", "--tag", image, str(context))
            # Check the source-containing build stage, not just dist: secrets can leak into layers.
            check = (
                "const fs = require('fs'); const paths = " + json.dumps(probes) + ";"
                "for (const path of paths) {"
                "if (fs.existsSync('/app/' + path)) throw Error('probe entered image: ' + path); }"
                "if (!fs.existsSync('/app/dist/index.html')) throw Error('missing static index');"
            )
            run("run", "--rm", "--entrypoint", "node", image, "-e", check)
            output = workspace / "assets"
            run(
                "build", "--target", "assets", "--output", f"type=local,dest={output}", str(context)
            )
        index = (output / "index.html").read_text(encoding="utf-8")
        if "/assets/" not in index or "/src/main.tsx" in index or "/@vite/client" in index:
            raise RuntimeError(
                "static output must reference compiled assets without the dev client"
            )
        if not list((output / "assets").glob("*.js")):
            raise RuntimeError("compiled JavaScript is missing")
        forbidden = ["src", "node_modules", "package.json", *probes]
        if any((output / name).exists() for name in forbidden):
            raise RuntimeError("asset export contains development or private files")
        print(f"Static asset build and context exclusion passed; evidence: {workspace}")
    finally:
        # Cleanup cannot replace a build failure; the unique workspace retains the build log.
        try:
            result = subprocess.run(
                ["docker", "image", "rm", image], capture_output=True, text=True, check=False
            )
            if result.returncode:
                print(f"Smoke image cleanup incomplete: {image}; log: {log_path}")
        except OSError:
            print(f"Smoke image cleanup unavailable: {image}; log: {log_path}")


if __name__ == "__main__":
    main()
