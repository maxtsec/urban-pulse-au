"""Verify the web allowlist against adversarial and actual working-tree contexts."""

import json
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BUILD_FILES = {
    "package.json",
    "package-lock.json",
    "index.html",
    "tsconfig.json",
    "vite.config.ts",
    "Caddyfile",
}
GENERATED_DIRECTORIES = {"node_modules", "dist"}
PROBES = (
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
    "service-account.json",
    "certificate.p12",
    "id_rsa",
    "test-results/trace.zip",
    "test-results/screenshot.png",
    "unknown.js",
    "src/service-account.json",
    "src/certificate.p12",
    "src/id_rsa",
    "src/unknown.ts",
    "src/assets/unknown.svg",
    "src/empty-directory/.keep",
)


def copy_tracked_context(web: Path, context: Path, tracked: list[str]) -> set[str]:
    """Use working-tree contents; absent tracked paths represent unstaged deletions."""
    expected = set(BUILD_FILES)
    for name in tracked:
        relative = PurePosixPath(name)
        source = web / relative
        if not source.resolve().is_relative_to(web.resolve()):
            raise RuntimeError("web source must remain inside its build context")
        if not source.exists():
            print(f"Skipping deleted tracked web file: {name}")
            continue
        destination = context / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        if relative.parts[0] == "src":
            expected.add(name)
    return expected


def verify_inventory(actual: set[str], expected_files: set[str]) -> None:
    """Check every source entry, including empty directories; build outputs are separate."""
    expected = expected_files | GENERATED_DIRECTORIES
    for name in expected_files:
        expected.update(str(p) for p in PurePosixPath(name).parents if str(p) != ".")
    unexpected = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unexpected or missing:
        raise RuntimeError(f"build inventory mismatch: unexpected={unexpected}; missing={missing}")


def main() -> None:
    identity = uuid4().hex
    workspace = (ROOT / ".local" / "web-build-smoke" / identity).resolve()
    if not workspace.is_relative_to(ROOT):
        raise RuntimeError("smoke output must remain inside the repository")
    web = ROOT / "apps" / "web"
    context = workspace / "context"
    context.mkdir(parents=True)
    tracked = (
        subprocess.check_output(["git", "ls-files", "-z", "--", "."], cwd=web).decode().split("\0")
    )
    expected = copy_tracked_context(web, context, list(filter(None, tracked)))
    written: set[Path] = set()
    for name in PROBES:
        path = context / name
        if path in written:
            continue  # Windows treats differently cased probe names as the same path.
        if path.exists():
            raise RuntimeError(f"synthetic probe would overwrite a tracked file: {name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// SYNTHETIC_BUILD_CONTEXT_PROBE", encoding="utf-8")
        written.add(path)
    image = "urbanpulse-web-build-smoke:" + identity
    log_path = workspace / "docker.log"
    try:
        with log_path.open("w", encoding="utf-8") as log:

            def run(*args: str, capture: bool = False) -> str:
                result = subprocess.run(
                    ["docker", *args],
                    cwd=ROOT,
                    stdout=subprocess.PIPE if capture else log,
                    stderr=log,
                    text=True,
                    check=True,
                )
                return result.stdout if capture else ""

            # Fail on adversarial inputs before building the actual workstation context.
            for label, build_context in (("adversarial", context), ("working-tree", web)):
                log.write(f"Checking {label} context\n")
                log.flush()
                run("build", "--target", "build", "--tag", image, str(build_context))
                check = """
const fs = require('fs');
const entries = [];
function visit(relative) {
  for (const entry of fs.readdirSync('/app/' + relative, {withFileTypes: true})) {
    const name = relative + entry.name;
    entries.push(name);
    if (entry.isSymbolicLink()) throw Error('unexpected source symlink: ' + name);
    if (entry.isDirectory() && !['node_modules', 'dist'].includes(name)) visit(name + '/');
  }
}
visit('');
if (!fs.existsSync('/app/dist/index.html')) throw Error('missing static index');
process.stdout.write(JSON.stringify(entries));
"""
                inventory = json.loads(
                    run("run", "--rm", "--entrypoint", "node", image, "-e", check, capture=True)
                )
                verify_inventory(set(inventory), expected)
                (workspace / f"{label}-inventory.json").write_text(
                    json.dumps(sorted(inventory), indent=2), encoding="utf-8"
                )
            output = workspace / "assets"
            run("build", "--target", "assets", "--output", f"type=local,dest={output}", str(web))
        index = (output / "index.html").read_text(encoding="utf-8")
        if "/assets/" not in index or "/src/main.tsx" in index or "/@vite/client" in index:
            raise RuntimeError(
                "static output must reference compiled assets without the dev client"
            )
        if not list((output / "assets").glob("*.js")):
            raise RuntimeError("compiled JavaScript is missing")
        if {p.name for p in output.iterdir()} != {"index.html", "assets"}:
            raise RuntimeError("asset export contains unexpected top-level entries")
        print(f"Static assets and both complete build inventories passed; evidence: {workspace}")
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
