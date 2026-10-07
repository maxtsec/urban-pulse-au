"""Host gate failure cases; real kernel/mount behaviour is an operator drill."""

import json
import stat
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import collector_host as host

FS = "11111111-1111-4111-8111-111111111111"
LUKS = "22222222-2222-4222-8222-222222222222"
IMAGE = "sha256:" + "a" * 64
DM = "CRYPT-LUKS2-" + LUKS.replace("-", "") + "-urbanpulse-data"


def row():
    return dict(
        target="/srv/urbanpulse",
        source="/dev/mapper/urbanpulse-data",
        fstype="ext4",
        fsroot="/",
        uuid=FS,
        options="rw,nosuid,nodev,noexec",
        **{"maj:min": "253:0"},
    )


@pytest.mark.parametrize(
    "change",
    [
        {"target": "/"},
        {"fstype": "overlay"},
        {"fstype": "tmpfs"},
        {"fsroot": "/subdirectory"},
        {"uuid": LUKS},
        {"options": "ro,nodev,nosuid,noexec"},
        {"options": "rw"},
    ],
)
def test_wrong_or_unprotected_mount_is_refused(change):
    with pytest.raises(host.HostRefused):
        host.validate_mount(row() | change, FS, LUKS, DM)


@pytest.mark.parametrize(
    "dm", ["", "LVM-plain-volume", DM.replace("LUKS2", "PLAIN"), DM + "-other"]
)
def test_filesystem_uuid_alone_does_not_prove_encryption(dm):
    with pytest.raises(host.HostRefused):
        host.validate_mount(row(), FS, LUKS, dm)


def test_matching_encrypted_root_is_accepted():
    host.validate_mount(row(), FS, LUKS, DM)


@pytest.fixture
def kernel(monkeypatch):
    monkeypatch.setattr(host.Path, "resolve", lambda p, **_: p)
    monkeypatch.setattr(host, "mounted", lambda *_: row())
    monkeypatch.setattr(host.os, "major", lambda _: 253, raising=False)
    monkeypatch.setattr(host.os, "minor", lambda _: 0, raising=False)

    def metadata(p):
        if p.as_posix() == "/dev/mapper/urbanpulse-data":
            return SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=1)
        return SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=10001, st_gid=10001)

    monkeypatch.setattr(host.Path, "stat", metadata)

    def read(p, **_):
        return "Filename Type Size Used Priority\n" if p.as_posix() == "/proc/swaps" else DM

    monkeypatch.setattr(host.Path, "read_text", read)
    return dict(filesystem_uuid=FS, luks_uuid=LUKS, image_id=IMAGE)


def test_no_writes_or_docker_needed_to_check_mount(kernel):
    host.check(kernel)


def test_active_swap_refuses_run(kernel, monkeypatch):
    read = host.Path.read_text
    monkeypatch.setattr(
        host.Path,
        "read_text",
        lambda p, **kw: (
            "header\n/swap.img file 100 0 -2\n" if p.as_posix() == "/proc/swaps" else read(p, **kw)
        ),
    )
    with pytest.raises(host.HostRefused, match="swap"):
        host.check(kernel)


def test_shadow_store_mount_refuses_run(kernel, monkeypatch):
    monkeypatch.setattr(
        host,
        "mounted",
        lambda kind, *_: (
            row() if kind == "--mountpoint" else row() | {"target": "/srv/urbanpulse/store-v3"}
        ),
    )
    with pytest.raises(host.HostRefused, match="shadow"):
        host.check(kernel)


def test_mutable_image_tag_refuses_run(kernel):
    with pytest.raises(host.HostRefused, match="pinned"):
        host.check(kernel | {"image_id": "urbanpulse-capture:latest"})


def test_locked_volume_never_invokes_docker(monkeypatch, capsys):
    monkeypatch.setattr(host.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(
        host.Path,
        "lstat",
        lambda _: SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0, st_size=100),
    )
    monkeypatch.setattr(
        host.Path,
        "read_text",
        lambda *a, **kw: json.dumps(dict(filesystem_uuid=FS, luks_uuid=LUKS, image_id=IMAGE)),
    )
    monkeypatch.setattr(host.Path, "resolve", lambda p, **kw: p)
    monkeypatch.setattr(
        host, "mounted", Mock(side_effect=host.subprocess.CalledProcessError(1, "findmnt"))
    )
    execute = Mock()
    monkeypatch.setattr(host.os, "execv", execute)
    monkeypatch.setattr("sys.argv", ["collector_host.py", "run"])
    assert host.main() == 2
    execute.assert_not_called()
    assert capsys.readouterr().out.startswith("collector_host_refused")


def test_launcher_is_bounded_offline_and_has_no_key_or_init_side_effect():
    args = host.docker_command("run", IMAGE)
    assert args[args.index("--network") + 1] == "none"
    assert args[args.index("--memory") + 1] == args[args.index("--memory-swap") + 1]
    assert args[args.index("--store-version") + 1] == "v3"
    assert args[-4:] == ["--max-attempts", "6", "--max-seconds", "120"]
    assert "--live" not in args and "--key-file" not in args and "init" not in args
    assert "--pull=never" in args and IMAGE in args
