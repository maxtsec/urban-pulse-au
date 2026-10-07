"""Host supervisor survives Docker outages; only systemd owns restart intent."""

import argparse
import json
import signal
import stat
import subprocess
from threading import Event

from scripts import collector_host as host

NAME = "urbanpulse-capture-continuous"
LABEL = "au.urbanpulse.collector=continuous"
KEY = host.MOUNT / "keys" / "transport-victoria"


def command(config: dict[str, str], live: bool) -> list[str]:
    args = host.docker_command("serve", config["image_id"])
    args[args.index(host.NAME)] = NAME
    at = args.index(config["image_id"])
    args[at:at] = ["--label", LABEL]
    if live:
        metadata = KEY.lstat()
        if (
            KEY.resolve(strict=True) != KEY
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 10001
            or metadata.st_gid != 10001
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 1024
            or host.mounted("--target", str(KEY)) != host.mounted("--mountpoint", str(host.MOUNT))
        ):
            raise host.HostRefused("private_encrypted_key_required")
        args[args.index("--network") + 1] = "bridge"
        at = args.index(config["image_id"])
        args[at:at] = ["--mount", f"type=bind,src={KEY},dst=/run/dtp-key,readonly"]
        args += ["--live", "--key-file", "/run/dtp-key"]
    return args


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/usr/bin/docker", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=45 if args[0] == "stop" else 15,
    )


def owned_container(image: str, live: bool = False) -> bool | None:
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
    if config.get("Cmd") != expected:
        raise host.HostRefused("container_mode_mismatch")
    running: bool = state["Running"]
    return running


def supervise(stop: Event, *, live: bool) -> int:
    """No dependency on docker.service lifetime, no persisted desired-run flag."""
    child: subprocess.Popen[bytes] | None = None
    image: str | None = None
    try:
        while not stop.is_set():
            try:
                config = host.configuration()  # Repeat after every daemon/process loss.
                image = config["image_id"]
                args = command(config, live)
                running = owned_container(image, live)
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
                    print("collector_configuration_refused", flush=True)
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
                if owned_container(image, live):
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
    args = parser.parse_args()
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    return supervise(stop, live=args.live)


if __name__ == "__main__":
    raise SystemExit(main())
