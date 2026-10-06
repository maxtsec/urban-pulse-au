"""Memory is cgroup-wide evidence; unavailable is never reported as zero."""

import json
from pathlib import Path

import pytest

from workers.job_observation import CgroupMemory, JobObservation, number


def layout(tmp_path, version="v2", member="/", root="/"):
    proc = tmp_path / "proc"
    proc.mkdir()
    mount = tmp_path / "memory mount"
    mount.mkdir()
    escaped = str(mount).replace(" ", chr(92) + "040")
    group = "0::" if version == "v2" else "5:cpu,memory:"
    (proc / "cgroup").write_text(group + member + "\n")
    fs = "cgroup2 cgroup rw" if version == "v2" else "cgroup cgroup rw,memory"
    (proc / "mountinfo").write_text(f"1 2 0:1 {root} {escaped} rw - {fs}\n")
    relative = Path(member.removeprefix(root).lstrip("/")) if member != "/" else Path(".")
    target = mount / relative
    target.mkdir(parents=True, exist_ok=True)
    return proc, target


@pytest.mark.parametrize("version", ["v1", "v2"])
@pytest.mark.parametrize(
    "member,root", [("/", "/"), ("/parent/job", "/parent"), ("/", "/host/container")]
)
def test_resolves_current_memory_cgroup_and_escaped_mount(tmp_path, version, member, root):
    proc, target = layout(tmp_path, version, member, root)
    current = "memory.current" if version == "v2" else "memory.usage_in_bytes"
    peak = "memory.peak" if version == "v2" else "memory.max_usage_in_bytes"
    (target / current).write_text("1024")
    (target / peak).write_text("8192")
    memory = CgroupMemory.discover(proc)
    assert memory == CgroupMemory(target, version)
    assert memory.current() == 1024
    assert memory.peak() == 8192


@pytest.mark.parametrize("value", ["max", "-1", "bad", ""])
def test_invalid_measurements_are_unknown(tmp_path, value):
    path = tmp_path / "counter"
    path.write_text(value)
    assert number(path) is None
    assert number(tmp_path / "absent") is None


def test_sampling_fallback_does_not_invent_native_peak(tmp_path, monkeypatch, capsys):
    proc, target = layout(tmp_path)
    current = target / "memory.current"
    current.write_text("10")
    memory = CgroupMemory.discover(proc)
    monkeypatch.setattr(CgroupMemory, "discover", lambda: memory)
    observation = JobObservation(540)
    current.write_text("90")
    observation.sample()
    current.write_text("20")
    observation.begin_cleanup()
    observation.finish("complete")
    logs = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    assert [line["event"] for line in logs] == ["job_runner_started", "job_runner_finished"]
    assert logs[0]["invocation_id"] == logs[1]["invocation_id"]
    assert logs[1]["memory"]["sampled_max_bytes"] == 90
    assert logs[1]["memory"]["cgroup_lifetime_peak_bytes"] is None
    assert 0 <= logs[1]["cleanup_elapsed_seconds"] <= logs[1]["runner_elapsed_seconds"]


def test_native_peak_retains_short_child_spike_after_current_drops(tmp_path, monkeypatch, capsys):
    proc, target = layout(tmp_path)
    (target / "memory.current").write_text("10")
    peak = target / "memory.peak"
    peak.write_text("100")
    monkeypatch.setattr(CgroupMemory, "discover", lambda: CgroupMemory(target, "v2"))
    observation = JobObservation(540)
    peak.write_text("900")  # Kernel retains a spike missed by polling.
    observation.finish("complete")
    record = json.loads(capsys.readouterr().err.splitlines()[-1])["memory"]
    assert record["cgroup_peak_at_runner_entry_bytes"] == 100
    assert record["cgroup_lifetime_peak_bytes"] == 900
    assert record["sampled_max_bytes"] == 10


def test_missing_or_unsafe_cgroup_is_unavailable(tmp_path, monkeypatch, capsys):
    assert CgroupMemory.discover(tmp_path) is None
    proc, target = layout(tmp_path, member="/../outside")
    (target / "memory.current").write_text("999")
    assert CgroupMemory.discover(proc) is None
    monkeypatch.setattr(CgroupMemory, "discover", lambda: None)
    observation = JobObservation(1)
    observation.finish("interrupted")
    memory = json.loads(capsys.readouterr().err.splitlines()[-1])["memory"]
    assert memory["source"] == "unavailable"
    assert memory["sampled_max_bytes"] is None
    assert memory["sample_count"] == 0


def test_logging_failure_does_not_change_execution(monkeypatch):
    def broken(*args, **kwargs):
        raise BrokenPipeError("sensitive sink detail")

    monkeypatch.setattr("builtins.print", broken)
    JobObservation(1).finish("complete")


def test_supervision_failure_has_sanitized_finish_record(monkeypatch, capsys):
    from workers.job_runtime import supervise

    class Request:
        timeout_seconds = 1

    def failed(*args):
        raise RuntimeError("sensitive database URL")

    monkeypatch.setattr("workers.job_runtime._supervise", failed)
    with pytest.raises(RuntimeError):
        supervise(Request(), None, None)
    stderr = capsys.readouterr().err
    assert "sensitive" not in stderr
    assert json.loads(stderr.splitlines()[-1])["outcome"] == "execution-failed"


def test_deadline_offset_and_cleanup_use_monotonic_clock(monkeypatch, capsys):
    from unittest.mock import Mock

    monkeypatch.setattr(CgroupMemory, "discover", lambda: None)
    monkeypatch.setattr("workers.job_observation.perf_counter", Mock(side_effect=[10, 12, 15, 18]))
    observation = JobObservation(540)
    observation.arm_deadline()
    observation.begin_cleanup()
    observation.finish("deadline-exceeded")
    record = json.loads(capsys.readouterr().err.splitlines()[-1])
    assert record["deadline_offset_seconds"] == 2
    assert record["cleanup_elapsed_seconds"] == 3
    assert record["runner_elapsed_seconds"] == 8
