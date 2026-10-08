"""Supervisor lifecycle with replaceable Docker boundary; no host provisioning."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import collector_service as service

IMAGE = "sha256:" + "a" * 64
CONFIG = {"image_id": IMAGE}
ACCOUNT = "collector@example-capture.iam.gserviceaccount.com"


class Stop:
    def __init__(self, waits=5):
        self.remaining = waits
        self.stopped = False

    def is_set(self):
        return self.stopped

    def wait(self, seconds):
        self.remaining -= 1
        self.stopped = self.remaining <= 0
        return self.stopped


@pytest.fixture
def boundary(monkeypatch):
    configure = Mock(return_value=CONFIG)
    monkeypatch.setattr(service.host, "configuration", configure)
    monkeypatch.setattr(service, "command", lambda *_: ["fixture-docker"])
    monkeypatch.setattr(service, "owned_container", Mock(return_value=None))
    launch = Mock(return_value=SimpleNamespace(poll=lambda: 1, wait=lambda: 1))
    monkeypatch.setattr(service.subprocess, "Popen", launch)
    return configure, launch


def test_docker_outage_then_return_rechecks_guard_and_resumes(boundary, monkeypatch):
    configure, launch = boundary
    inspect = Mock(side_effect=[OSError("offline"), None, None, None])
    monkeypatch.setattr(service, "owned_container", inspect)
    assert service.supervise(Stop(3), live=False) == 0
    assert configure.call_count == 3 and launch.call_count == 2


def test_locked_volume_after_daemon_loss_never_launches_again(boundary):
    configure, launch = boundary
    configure.side_effect = [CONFIG, service.host.HostRefused("locked")]
    assert service.supervise(Stop(), live=False) == 78
    assert launch.call_count == 1


def test_manual_stop_has_no_restart_or_persisted_intent(boundary):
    configure, launch = boundary
    assert service.supervise(Stop(1), live=False) == 0
    assert launch.call_count == configure.call_count == 1
    launch.reset_mock()
    stopped = Stop(0)
    stopped.stopped = True
    assert service.supervise(stopped, live=False) == 0
    launch.assert_not_called()


def test_live_restore_attaches_existing_owned_process_without_second_writer(boundary, monkeypatch):
    _, launch = boundary
    monkeypatch.setattr(service, "owned_container", Mock(side_effect=[True, None]))
    assert service.supervise(Stop(1), live=False) == 0
    assert launch.call_args.args[0] == [
        "/usr/bin/docker",
        "attach",
        "--sig-proxy=false",
        service.NAME,
    ]


def test_operator_required_exit_stays_stopped(boundary):
    _, launch = boundary
    launch.return_value = SimpleNamespace(poll=lambda: 78, wait=lambda: 78)
    assert service.supervise(Stop(), live=False) == 78
    assert launch.call_count == 1


def test_stopped_owned_container_removed_without_force_before_restart(boundary, monkeypatch):
    monkeypatch.setattr(service, "owned_container", Mock(side_effect=[False, None]))
    docker = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(service, "docker", docker)
    assert service.supervise(Stop(1), live=False) == 0
    docker.assert_called_once_with("rm", service.NAME)


@pytest.mark.parametrize("image,label", [("other", "continuous"), (IMAGE, "other")])
def test_unowned_name_is_never_removed_or_attached(image, label, monkeypatch):
    row = {
        "Image": image,
        "Config": {"Labels": {"au.urbanpulse.collector": label}},
        "State": {"Running": True},
    }
    docker = Mock(
        side_effect=[
            SimpleNamespace(returncode=0, stdout="id"),
            SimpleNamespace(returncode=0, stdout=json.dumps([row])),
        ]
    )
    monkeypatch.setattr(service, "docker", docker)
    with pytest.raises(service.host.HostRefused):
        service.owned_container(IMAGE)
    assert docker.call_count == 2


def test_fixture_launch_is_networkless_capped_and_v3():
    args = service.command(CONFIG, False)
    assert args[args.index("--network") + 1] == "none"
    assert args[args.index("--memory") + 1] == "512m"
    assert args[args.index("--memory-swap") + 1] == "512m"
    assert args[-5:] == ["serve", "--store", "/data", "--store-version", "v3"]
    assert "--live" not in args and service.LABEL in args


@pytest.mark.parametrize("live", [False, True])
def test_owned_container_mode_is_checked_before_adoption(live, monkeypatch):
    row = {
        "Image": IMAGE,
        "Config": {
            "Labels": {"au.urbanpulse.collector": "continuous"},
            "Cmd": ["serve", "--store", "/data", "--store-version", "v3"],
        },
        "State": {"Running": True},
    }
    docker = Mock(
        side_effect=[
            SimpleNamespace(returncode=0, stdout="id"),
            SimpleNamespace(returncode=0, stdout=json.dumps([row])),
        ]
    )
    monkeypatch.setattr(service, "docker", docker)
    if live:
        with pytest.raises(service.host.HostRefused, match="mode"):
            service.owned_container(IMAGE, live)
    else:
        assert service.owned_container(IMAGE, live) is True


def test_manual_stop_signals_owned_running_container_and_waits(boundary, monkeypatch):
    _, launch = boundary
    child = Mock()
    child.poll.return_value = None
    launch.return_value = child
    monkeypatch.setattr(service, "owned_container", Mock(side_effect=[None, True]))
    docker = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(service, "docker", docker)
    assert service.supervise(Stop(1), live=False) == 0
    docker.assert_called_once_with("stop", "--time", "30", service.NAME)
    child.terminate.assert_called_once()
    child.wait.assert_called_once_with(timeout=5)


def test_live_key_outside_encrypted_mount_is_refused(monkeypatch):
    import stat

    monkeypatch.setattr(
        service.host.Path,
        "lstat",
        lambda _: SimpleNamespace(
            st_mode=stat.S_IFREG | 0o600, st_uid=10001, st_gid=10001, st_size=64
        ),
    )
    monkeypatch.setattr(service.host.Path, "resolve", lambda p, **kw: p)
    monkeypatch.setattr(service.host, "mounted", lambda kind, *_: {"target": kind})
    with pytest.raises(service.host.HostRefused, match="key"):
        service.command(CONFIG, True)


@pytest.fixture
def private_keys(monkeypatch):
    import stat

    monkeypatch.setattr(
        service.Path,
        "lstat",
        lambda _: SimpleNamespace(
            st_mode=stat.S_IFREG | 0o600, st_uid=10001, st_gid=10001, st_size=64
        ),
    )
    monkeypatch.setattr(service.Path, "resolve", lambda path, **_: path)
    monkeypatch.setattr(service.host, "mounted", lambda *_: {"source": "encrypted"})


def test_monitoring_launch_binds_only_two_readonly_keys(private_keys, monkeypatch):
    from io import BytesIO

    monkeypatch.setattr(
        service.Path,
        "open",
        lambda *_: BytesIO(
            json.dumps(
                {
                    "type": "service_account",
                    "project_id": "example-capture",
                    "client_email": ACCOUNT,
                }
            ).encode()
        ),
    )
    args = service.command(CONFIG, True, "example-capture", "pilot", ACCOUNT)
    mounts = [args[index + 1] for index, arg in enumerate(args) if arg == "--mount"]
    assert f"type=bind,src={service.KEY},dst=/run/dtp-key,readonly" in mounts
    assert (
        f"type=bind,src={service.MONITORING_KEY},dst=/run/collector-upload.json,readonly" in mounts
    )
    assert args[-8:] == [
        "--monitoring-project",
        "example-capture",
        "--monitoring-collector",
        "pilot",
        "--monitoring-service-account",
        ACCOUNT,
        "--monitoring-key-file",
        "/run/collector-upload.json",
    ]
    assert args[args.index("--network") + 1] == "bridge"
    assert "private_key" not in " ".join(args)


@pytest.mark.parametrize(
    "project,collector,live",
    [
        ("example-capture", None, True),
        (None, "pilot", True),
        ("../other", "pilot", True),
        ("example-capture", "pilot", False),
    ],
)
def test_invalid_monitoring_launch_cannot_start_docker(project, collector, live):
    with pytest.raises(service.host.HostRefused):
        service.command(CONFIG, live, project, collector)


@pytest.mark.parametrize("bad", ["uid", "mode", "size", "symlink", "mount"])
def test_monitoring_key_must_be_private_on_same_encrypted_volume(private_keys, monkeypatch, bad):
    import stat

    def metadata(path):
        values = {"st_mode": stat.S_IFREG | 0o600, "st_uid": 10001, "st_gid": 10001, "st_size": 64}
        if path == service.MONITORING_KEY:
            if bad == "uid":
                values["st_uid"] = 0
            if bad == "mode":
                values["st_mode"] = stat.S_IFREG | 0o644
            if bad == "size":
                values["st_size"] = 16385
            if bad == "symlink":
                values["st_mode"] = stat.S_IFLNK | 0o600
        return SimpleNamespace(**values)

    monkeypatch.setattr(service.Path, "lstat", metadata)
    if bad == "mount":
        monkeypatch.setattr(
            service.host,
            "mounted",
            lambda _, path: {
                "source": "other" if path == str(service.MONITORING_KEY) else "encrypted"
            },
        )
    with pytest.raises(service.host.HostRefused, match="key"):
        service.command(CONFIG, True, "example-capture", "pilot", ACCOUNT)


def test_adoption_refuses_existing_process_with_different_monitoring_target(monkeypatch):
    row = {
        "Image": IMAGE,
        "Config": {
            "Labels": {"au.urbanpulse.collector": "continuous"},
            "Cmd": [
                "serve",
                "--store",
                "/data",
                "--store-version",
                "v3",
                "--live",
                "--key-file",
                "/run/dtp-key",
                *service.monitoring_arguments("example-capture", "other", ACCOUNT),
            ],
        },
        "State": {"Running": True},
    }
    monkeypatch.setattr(
        service,
        "docker",
        Mock(
            side_effect=[
                SimpleNamespace(returncode=0, stdout="id"),
                SimpleNamespace(returncode=0, stdout=json.dumps([row])),
            ]
        ),
    )
    with pytest.raises(service.host.HostRefused, match="mode"):
        service.owned_container(IMAGE, True, "example-capture", "pilot", ACCOUNT)


@pytest.mark.parametrize(
    "email",
    [
        "deployer@example-capture.iam.gserviceaccount.com",
        "collector-extra@example-capture.iam.gserviceaccount.com",
        None,
    ],
)
def test_supervisor_rejects_wrong_key_identity_before_launch(private_keys, monkeypatch, email):
    from io import BytesIO

    monkeypatch.setattr(
        service.Path,
        "open",
        lambda *_: BytesIO(
            json.dumps(
                {
                    "type": "service_account",
                    "project_id": "example-capture",
                    "client_email": email,
                }
            ).encode()
        ),
    )
    with pytest.raises(service.host.HostRefused, match="identity"):
        service.command(CONFIG, True, "example-capture", "pilot", ACCOUNT)


def test_adoption_requires_exact_configured_service_account(monkeypatch):
    row = {
        "Image": IMAGE,
        "Config": {
            "Labels": {"au.urbanpulse.collector": "continuous"},
            "Cmd": [
                "serve",
                "--store",
                "/data",
                "--store-version",
                "v3",
                "--live",
                "--key-file",
                "/run/dtp-key",
                *service.monitoring_arguments(
                    "example-capture", "pilot", "deployer@example-capture.iam.gserviceaccount.com"
                ),
            ],
        },
        "State": {"Running": True},
    }
    monkeypatch.setattr(
        service,
        "docker",
        Mock(
            side_effect=[
                SimpleNamespace(returncode=0, stdout="id"),
                SimpleNamespace(returncode=0, stdout=json.dumps([row])),
            ]
        ),
    )
    with pytest.raises(service.host.HostRefused, match="mode"):
        service.owned_container(IMAGE, True, "example-capture", "pilot", ACCOUNT)


def test_supervisor_requires_explicit_service_account_even_with_valid_project_and_alias():
    with pytest.raises(service.host.HostRefused):
        service.command(CONFIG, True, "example-capture", "pilot")
