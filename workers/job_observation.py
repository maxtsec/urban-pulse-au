"""Best-effort runner timing and cgroup memory evidence, independent of job outcomes."""

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from time import perf_counter
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def number(path: Path) -> int | None:
    try:
        value = int(path.read_text(encoding="ascii").strip())
        return value if value >= 0 else None
    except (OSError, ValueError):
        return None


def unescape(value: str) -> str:
    for code in (32, 9, 10, 92):
        value = value.replace(chr(92) + format(code, "03o"), chr(code))
    return value


@dataclass(frozen=True)
class CgroupMemory:
    directory: Path
    version: str

    @classmethod
    def discover(cls, proc: Path = Path("/proc/self")) -> "CgroupMemory | None":
        try:
            memberships = [
                line.split(":", 2) for line in (proc / "cgroup").read_text().splitlines()
            ]
            mounts = (proc / "mountinfo").read_text().splitlines()
            for version, filesystem, controller in (
                ("v2", "cgroup2", ""),
                ("v1", "cgroup", "memory"),
            ):
                for _, controllers, member in memberships:
                    if (version == "v2" and controllers) or (
                        version == "v1" and controller not in controllers.split(",")
                    ):
                        continue
                    membership = PurePosixPath(member)
                    if not membership.is_absolute() or ".." in membership.parts:
                        continue
                    for mount in mounts:
                        left, right = mount.split(" - ", 1)
                        fields, options = left.split(), right.split()
                        if options[0] != filesystem or (
                            version == "v1" and "memory" not in options[2].split(",")
                        ):
                            continue
                        root = PurePosixPath(unescape(fields[3]))
                        if membership == PurePosixPath("/"):
                            relative = PurePosixPath(".")  # Cgroup namespace root.
                        elif membership.is_relative_to(root):
                            relative = membership.relative_to(root)
                        else:
                            continue
                        directory = Path(unescape(fields[4])).joinpath(*relative.parts)
                        candidate = cls(directory, version)
                        if candidate.current() is not None or candidate.peak() is not None:
                            return candidate
        except (OSError, ValueError, IndexError):
            pass
        return None

    def current(self) -> int | None:
        return number(
            self.directory / ("memory.current" if self.version == "v2" else "memory.usage_in_bytes")
        )

    def peak(self) -> int | None:
        return number(
            self.directory
            / ("memory.peak" if self.version == "v2" else "memory.max_usage_in_bytes")
        )


def emit_observation(record: dict[str, object]) -> None:
    try:
        print(
            json.dumps({"severity": "INFO", "telemetry_version": 1, **record}),
            file=sys.stderr,
            flush=True,
        )
    except (OSError, ValueError):
        # A missing metric/log sink must never cause a mutation to be retried.
        pass


class JobObservation:
    def __init__(self, timeout_seconds: int) -> None:
        self.entered_at = utc_now()
        self.started = perf_counter()
        self.invocation_id = uuid4().hex
        self.memory = CgroupMemory.discover()
        self.baseline_peak = self.memory.peak() if self.memory else None
        self.sampled_peak: int | None = None
        self.samples = 0
        self.cleanup_started: float | None = None
        self.deadline_started_at: str | None = None
        self.deadline_offset_seconds: float | None = None
        self.sample()
        emit_observation(
            {
                "event": "job_runner_started",
                "invocation_id": self.invocation_id,
                "runner_entered_at": self.entered_at,
                "timeout_seconds": timeout_seconds,
            }
        )

    def sample(self) -> None:
        value = self.memory.current() if self.memory else None
        if value is not None:
            self.sampled_peak = max(self.sampled_peak or 0, value)
            self.samples += 1

    def arm_deadline(self) -> None:
        self.deadline_started_at = utc_now()
        self.deadline_offset_seconds = perf_counter() - self.started

    def begin_cleanup(self) -> None:
        self.cleanup_started = perf_counter()

    def finish(self, outcome: str) -> None:
        self.sample()
        finished = perf_counter()
        emit_observation(
            {
                "event": "job_runner_finished",
                "invocation_id": self.invocation_id,
                "runner_entered_at": self.entered_at,
                "cleanup_completed_at": utc_now(),
                "outcome": outcome,
                "deadline_started_at": self.deadline_started_at,
                "deadline_offset_seconds": self.deadline_offset_seconds,
                "runner_elapsed_seconds": finished - self.started,
                "cleanup_elapsed_seconds": finished - self.cleanup_started
                if self.cleanup_started is not None
                else 0.0,
                "memory": {
                    "source": "cgroup_" + self.memory.version if self.memory else "unavailable",
                    "scope": "current_cgroup_including_descendants",
                    "cgroup_lifetime_peak_bytes": self.memory.peak() if self.memory else None,
                    "cgroup_peak_at_runner_entry_bytes": self.baseline_peak,
                    "sampled_max_bytes": self.sampled_peak,
                    "sample_count": self.samples,
                },
            }
        )
