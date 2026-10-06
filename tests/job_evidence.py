"""Validate additive stderr evidence without changing the terminal stdout contract."""

import json
from datetime import datetime


def check_job_evidence(stderr: str, status: str) -> None:
    if status == "invalid-job-arguments":
        assert not stderr
        return
    records = [json.loads(line) for line in stderr.splitlines()]
    assert len(records) == 2, stderr
    start, finish = records
    assert start["event"] == "job_runner_started"
    assert finish["event"] == "job_runner_finished"
    assert start["invocation_id"] == finish["invocation_id"]
    assert all(r["severity"] == "INFO" and r["telemetry_version"] == 1 for r in records)
    assert finish["outcome"] == status
    assert datetime.fromisoformat(start["runner_entered_at"]).tzinfo is not None
    assert datetime.fromisoformat(finish["cleanup_completed_at"]).tzinfo is not None
    assert 0 <= finish["cleanup_elapsed_seconds"] <= finish["runner_elapsed_seconds"]
    if finish["deadline_started_at"] is None:
        assert finish["deadline_offset_seconds"] is None
        assert status == "interrupted"
    else:
        assert datetime.fromisoformat(finish["deadline_started_at"]).tzinfo is not None
        assert 0 <= finish["deadline_offset_seconds"] <= finish["runner_elapsed_seconds"]
    memory = finish["memory"]
    assert memory["scope"] == "current_cgroup_including_descendants"
    for name in ("cgroup_lifetime_peak_bytes", "sampled_max_bytes"):
        assert memory[name] is None or memory[name] >= 0
