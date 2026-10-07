"""Guarded, offline host rehearsal. Uses only the Ubuntu Python standard library."""

import argparse
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from uuid import UUID

MOUNT = Path("/srv/urbanpulse")
STORE = MOUNT / "store-v3"
CONFIG = Path("/etc/urbanpulse/collector-host.json")
NAME = "urbanpulse-capture-rehearsal"


class HostRefused(ValueError):
    pass


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True, encoding="utf-8", timeout=10)


def validate_mount(row: dict, fs_uuid: str, luks_uuid: str, dm_uuid: str) -> None:
    options = set(row.get("options", "").split(","))
    if (
        row.get("target") != MOUNT.as_posix()
        or row.get("fstype") != "ext4"
        or row.get("fsroot") != "/"
        or row.get("uuid") != fs_uuid
        or not {"rw", "nodev", "nosuid", "noexec"} <= options
        or dm_uuid != f"CRYPT-LUKS2-{UUID(luks_uuid).hex}-urbanpulse-data"
    ):
        raise HostRefused("encrypted_mount_mismatch")


def mounted(*args: str) -> dict:
    rows = json.loads(
        output(
            "/usr/bin/findmnt",
            "--json",
            *args,
            "--output",
            "TARGET,SOURCE,FSTYPE,FSROOT,OPTIONS,UUID,MAJ:MIN",
        )
    )["filesystems"]
    if len(rows) != 1:
        raise HostRefused("ambiguous_mount")
    return rows[0]


def check(config: dict) -> None:
    fields = {"filesystem_uuid", "luks_uuid", "image_id"}
    if (
        not isinstance(config, dict)
        or set(config) != fields
        or any(not isinstance(value, str) for value in config.values())
    ):
        raise HostRefused("invalid_config")
    fs_uuid = str(UUID(config["filesystem_uuid"]))
    luks_uuid = str(UUID(config["luks_uuid"]))
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", config["image_id"]):
        raise HostRefused("pinned_local_image_required")
    if MOUNT.resolve(strict=True) != MOUNT or STORE.resolve(strict=True) != STORE:
        raise HostRefused("symlink_path")
    row = mounted("--mountpoint", MOUNT.as_posix())
    device = row["maj:min"]
    if not re.fullmatch(r"[0-9]+:[0-9]+", device):
        raise HostRefused("invalid_mount_device")
    dm_uuid = Path(f"/sys/dev/block/{device}/dm/uuid").read_text(encoding="utf-8").strip()
    validate_mount(row, fs_uuid, luks_uuid, dm_uuid)
    mapper = Path("/dev/mapper/urbanpulse-data").stat()
    if (
        not stat.S_ISBLK(mapper.st_mode)
        or device != f"{os.major(mapper.st_rdev)}:{os.minor(mapper.st_rdev)}"
    ):
        raise HostRefused("mapper_mismatch")
    if mounted("--target", STORE.as_posix()) != row:
        raise HostRefused("store_shadow_mount")
    directory = STORE.stat()
    if (
        not stat.S_ISDIR(directory.st_mode)
        or directory.st_uid != 10001
        or directory.st_gid != 10001
        or stat.S_IMODE(directory.st_mode) != 0o700
    ):
        raise HostRefused("store_permissions")
    if len(Path("/proc/swaps").read_text(encoding="utf-8").splitlines()) != 1:
        raise HostRefused("swap_must_be_disabled")


def docker_command(command: str, image: str) -> list[str]:
    args = [
        "/usr/bin/docker",
        "run",
        "--rm",
        "--pull=never",
        "--name",
        NAME,
        "--network",
        "none",
        "--read-only",
        "--user",
        "10001:10001",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "512m",
        "--memory-swap",
        "512m",
        "--ulimit",
        "core=0",
        "--stop-timeout",
        "30",
        "--log-driver",
        "local",
        "--log-opt",
        "max-size=10m",
        "--log-opt",
        "max-file=2",
        "--mount",
        f"type=bind,src={STORE},dst=/data,bind-propagation=rprivate",
        image,
        command,
        "--store",
        "/data",
        "--store-version",
        "v3",
    ]
    if command == "run":
        args += ["--max-attempts", "6", "--max-seconds", "120"]
    return args


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "init", "run", "status", "verify"))
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise HostRefused("root_operator_required")
        metadata = CONFIG.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 4096
        ):
            raise HostRefused("private_root_config_required")
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        check(config)
        if args.command == "check":
            print("collector_host_ready")
        else:
            os.execv("/usr/bin/docker", docker_command(args.command, config["image_id"]))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        # No private paths, UUIDs, configuration values or subprocess output in logs.
        print("collector_host_refused: check encrypted mount, identity, swap and configuration")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
