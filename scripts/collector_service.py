"""Host supervisor survives Docker outages; only systemd owns restart intent."""

import argparse
import json
import re
import signal
import stat
import subprocess
from pathlib import Path
from threading import Event

from scripts import collector_host as host

NAME = "urbanpulse-capture-continuous"
LABEL = "au.urbanpulse.collector=continuous"
KEY = host.MOUNT / "keys" / "transport-victoria"
MONITORING_KEY = host.MOUNT / "keys" / "collector-upload.json"


def monitoring_arguments(
    project: str | None, collector: str | None, service_account: str | None = None
) -> list[str]:
    if project is None and collector is None and service_account is None:
        return []
    if (
        project is None
        or collector is None
        or service_account is None
        or re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project) is None
        or re.fullmatch(r"[a-z][a-z0-9-]{0,62}", collector) is None
        or re.fullmatch(
            r"[a-z][a-z0-9-]{4,28}[a-z0-9]@" + re.escape(project) + r"\.iam\.gserviceaccount\.com",
            service_account,
        )
        is None
    ):
        raise host.HostRefused("invalid_monitoring_target")
    return [
        "--monitoring-project",
        project,
        "--monitoring-collector",
        collector,
        "--monitoring-service-account",
        service_account,
        "--monitoring-key-file",
        "/run/collector-upload.json",
    ]


def encrypted_key(path: Path, limit: int) -> None:
    metadata = path.lstat()
    if (
        path.resolve(strict=True) != path
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 10001
        or metadata.st_gid != 10001
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or not 0 < metadata.st_size <= limit
        or host.mounted("--target", str(path)) != host.mounted("--mountpoint", str(host.MOUNT))
    ):
        raise host.HostRefused("private_encrypted_key_required")


def monitoring_key_identity(project: str | None, service_account: str | None) -> None:
    # The mount/mode/size guard must run first. Do not log the parsed credential.
    with MONITORING_KEY.open("rb") as stream:
        content = stream.read(16385)
    try:
        value: object = json.loads(content)
    except (ValueError, UnicodeError):
        raise host.HostRefused("invalid_monitoring_key") from None
    if (
        len(content) > 16384
        or not isinstance(value, dict)
        or value.get("type") != "service_account"
        or value.get("project_id") != project
        or value.get("client_email") != service_account
    ):
        raise host.HostRefused("monitoring_key_identity_mismatch")


def command(
    config: dict[str, str],
    live: bool,
    project: str | None = None,
    collector: str | None = None,
    service_account: str | None = None,
) -> list[str]:
    monitoring = monitoring_arguments(project, collector, service_account)
    if monitoring and not live:
        raise host.HostRefused("monitoring_requires_live")
    args = host.docker_command("serve", config["image_id"])
    args[args.index(host.NAME)] = NAME
    at = args.index(config["image_id"])
    args[at:at] = ["--label", LABEL]
    if live:
        encrypted_key(KEY, 1024)
        args[args.index("--network") + 1] = "bridge"
        at = args.index(config["image_id"])
        args[at:at] = ["--mount", f"type=bind,src={KEY},dst=/run/dtp-key,readonly"]
        args += ["--live", "--key-file", "/run/dtp-key"]
    if monitoring:
        encrypted_key(MONITORING_KEY, 16384)
        monitoring_key_identity(project, service_account)
        at = args.index(config["image_id"])
        args[at:at] = [
            "--mount",
            f"type=bind,src={MONITORING_KEY},dst=/run/collector-upload.json,readonly",
        ]
        args += monitoring
    return args


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45 if args[0] == "stop" else 15,
    )


def owned_container(
    image: str,
    live: bool = False,
    project: str | None = None,
    collector: str | None = None,
    service_account: str | None = None,
) -> bool | None:
    """None = absent; bool = running. Only inspect/remove the exact owned name."""
    result = docker("container", "ls", "-a", "--filter", f"name=^/{NAME}$", "--format", "{{.ID}}")
    if result.returncode:
        raise OSError("docker_unavailable")
    if not result.stdout.strip():
        return None
    inspected = docker("container", "inspect", NAME)
    if inspected.returncode:
        raise OSError("docker_inspect_unavailable")
    value: object = json.loads(inspected.stdout)
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise host.HostRefused("invalid_container")
    row = value[0]
    config, state = row.get("Config"), row.get("State")
    if not isinstance(config, dict) or not isinstance(state, dict):
        raise host.HostRefused("invalid_container")
    labels = config.get("Labels")
    if (
        row.get("Image") != image
        or not isinstance(labels, dict)
        or labels.get("au.urbanpulse.collector") != "continuous"
        or not isinstance(state.get("Running"), bool)
    ):
        raise host.HostRefused("container_ownership_mismatch")
    expected = ["serve", "--store", "/data", "--store-version", "v3"]
    if live:
        expected += ["--live", "--key-file", "/run/dtp-key"]
    expected += monitoring_arguments(project, collector, service_account)
    if config.get("Cmd") != expected:
        raise host.HostRefused("container_mode_mismatch")
    running: bool = state["Running"]
    return running


def supervise(
    stop: Event,
    *,
    live: bool,
    project: str | None = None,
    collector: str | None = None,
    service_account: str | None = None,
) -> int:
    """No dependency on docker.service lifetime, no persisted desired-run flag."""
    child: subprocess.Popen[bytes] | None = None
    image: str | None = None
    try:
        while not stop.is_set():
            try:
                config = host.configuration()  # Repeat after every daemon/process loss.
                image = config["image_id"]
                args = command(config, live, project, collector, service_account)
                running = owned_container(image, live, project, collector, service_account)
                if running is False:
                    removed = docker("rm", NAME)  # Stopped owned container only, never force.
                    if removed.returncode:
                        raise OSError("container_cleanup_pending")
                if running:
                    args = ["/usr/bin/docker", "attach", "--sig-proxy=false", NAME]
                if stop.is_set():
                    break
                child = subprocess.Popen(args)
                while child.poll() is None and not stop.wait(1):
                    pass
                if stop.is_set():
                    break
                code = child.wait()
                child = None
                if code == 78:
                    print("collector_operator_required", flush=True)
                    return 78
            except host.HostRefused:
                print("collector_host_refused", flush=True)
                return 78
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
                print("collector_runtime_unavailable", flush=True)
            # Bounded retry rate, including Docker/containerd package restarts.
            if stop.wait(60):
                break
        return 0
    finally:
        if image is not None:
            try:
                if owned_container(image, live, project, collector, service_account):
                    if docker("stop", "--time", "30", NAME).returncode:
                        print("collector_stop_unconfirmed", flush=True)
            except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
                print("collector_stop_unconfirmed", flush=True)
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--monitoring-project")
    parser.add_argument("--monitoring-collector")
    parser.add_argument("--monitoring-service-account")
    args = parser.parse_args()
    try:
        monitoring = monitoring_arguments(
            args.monitoring_project, args.monitoring_collector, args.monitoring_service_account
        )
        if monitoring and not args.live:
            raise host.HostRefused("monitoring_requires_live")
    except host.HostRefused:
        parser.error("monitoring_requires_live_and_valid_project_collector_and_service_account")
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    return supervise(
        stop,
        live=args.live,
        project=args.monitoring_project,
        collector=args.monitoring_collector,
        service_account=args.monitoring_service_account,
    )


if __name__ == "__main__":
    raise SystemExit(main())
