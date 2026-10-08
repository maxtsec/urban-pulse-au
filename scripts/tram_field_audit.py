"""Bounded offline field census; read-only v3 input and a separate private report."""

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from google.protobuf import unknown_fields  # type: ignore[import-untyped]
from google.protobuf.message import DecodeError  # type: ignore[import-untyped]
from google.transit import gtfs_realtime_pb2 as gtfs

from urbanpulse.contracts.capture_control import Control, canonical
from urbanpulse.contracts.local_capture import FEEDS, MAX_BYTES, Intent, Manifest, Receipt

ROOT = Path(__file__).resolve().parents[1]
MAX_CAPTURES = 10_000
MAX_TOTAL_BYTES = 2 * 1024**3
MAX_FIELDS = 8192
MAX_VISITS = 20_000_000
MAX_SECONDS = 300


class AuditError(ValueError):
    """Fixed safe diagnostics, never payload data or credentials."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_file(root: Path, relative: str, limit: int = 16384) -> bytes:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise AuditError("input_path_escape")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise AuditError("input_symlink")
        if part == root:
            break
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise AuditError("input_size_or_type")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise AuditError("input_size_or_type")
    return data


def document(root: Path, relative: str) -> dict[str, Any]:
    value = json.loads(read_file(root, relative))
    if not isinstance(value, dict):
        raise AuditError("invalid_document")
    return value


class Census:
    def __init__(self) -> None:
        self.fields: dict[str, dict[str, Any]] = {}
        self.visits = 0
        self.deadline = time.monotonic() + MAX_SECONDS

    def check(self) -> None:
        if time.monotonic() >= self.deadline:
            raise AuditError("audit_deadline")

    def row(self, key: str, kind: str, capture: str) -> dict[str, Any]:
        self.visits += 1
        if self.visits > MAX_VISITS:
            raise AuditError("field_visit_limit")
        self.check()
        if key not in self.fields:
            if len(self.fields) >= MAX_FIELDS:
                raise AuditError("distinct_field_limit")
            self.fields[key] = dict(
                kind=kind,
                present=0,
                absent=0,
                explicit_default=0,
                captures_examined=0,
                captures_present=0,
                last_capture=None,
                last_present_capture=None,
                sample_captures=[],
            )
        row = self.fields[key]
        if row["last_capture"] != capture:
            row["captures_examined"] += 1
            row["last_capture"] = capture
        return row

    @staticmethod
    def present(row: dict[str, Any], capture: str) -> None:
        row["present"] += 1
        if row["last_present_capture"] != capture:
            row["captures_present"] += 1
            row["last_present_capture"] = capture
            if len(row["sample_captures"]) < 3:
                row["sample_captures"].append(capture)

    def inspect(self, message: Any, prefix: str, capture: str, depth: int = 0) -> bool:
        if depth > 32:
            raise AuditError("message_depth_limit")
        found_unknown = False
        present = {field.number: value for field, value in message.ListFields()}
        for field in message.DESCRIPTOR.fields:
            key = f"{prefix}.{field.name}#{field.number}"
            row = self.row(key, "known", capture)
            if field.number not in present:
                row["absent"] += 1
                continue
            self.present(row, capture)
            value = present[field.number]
            if field.message_type is not None:
                values = value if field.is_repeated else [value]
                for child in values:
                    found_unknown |= self.inspect(
                        child, key + ("[]" if field.is_repeated else ""), capture, depth + 1
                    )
            elif not field.is_repeated and value == field.default_value:
                row["explicit_default"] += 1
        for field in unknown_fields.UnknownFieldSet(message):
            known = message.DESCRIPTOR.fields_by_number.get(field.field_number)
            kind = "unknown_enum_or_wire" if known is not None else "unknown_wire_or_extension"
            key = f"{prefix}.unknown#{field.field_number}/wire{field.wire_type}"
            self.present(self.row(key, kind, capture), capture)
            found_unknown = True
        # Registered extensions can appear in ListFields but not descriptor.fields.
        for field, _ in message.ListFields():
            if field.is_extension:
                self.present(
                    self.row(f"{prefix}.extension#{field.number}", "registered_extension", capture),
                    capture,
                )
                found_unknown = True
        return found_unknown

    def report(self) -> dict[str, Any]:
        return {
            key: {k: v for k, v in row.items() if k not in {"last_capture", "last_present_capture"}}
            for key, row in sorted(self.fields.items())
        }


def control_at_start(root: Path) -> Control:
    marker = document(root, "store.json")
    if (
        set(marker) != {"schema_version", "store_id"}
        or marker["schema_version"] != "capture-store-v3"
    ):
        raise AuditError("v3_store_required")
    data = document(root, "control.json")
    checksum = data.pop("checksum", None)
    if checksum != digest(canonical(data)):
        raise AuditError("invalid_control_checksum")
    control = Control.model_validate(data)
    if str(control.store_id) != marker["store_id"]:
        raise AuditError("store_identity_mismatch")
    # This one-off reader is only valid before expiry is introduced/enabled.
    for name in ("expiry", "policies"):
        folder = root / name
        if folder.is_symlink() or not folder.is_dir() or next(folder.iterdir(), None) is not None:
            raise AuditError("expiry_or_retention_state_present")
    return control


def audit(
    root: Path, start: datetime, end: datetime, *, first: int = 1, last: int | None = None
) -> dict[str, Any]:
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or not timedelta(0) < end - start <= timedelta(hours=26)
    ):
        raise AuditError("invalid_interval")
    control = control_at_start(root)
    high_water = control.next_capture_sequence - 1 - int(control.pending is not None)
    last = high_water if last is None else last
    if first < 1 or last < first or last > high_water or last - first + 1 > MAX_CAPTURES:
        raise AuditError("invalid_or_unbounded_sequence_range")
    census = Census()
    inventory: list[list[Any]] = []
    inventory_hash = hashlib.sha256()
    feeds: dict[str, Any] = {
        feed: dict(outcomes=Counter(), entities=0, selected=0, modes=Counter(), received=[])
        for feed in FEEDS
    }
    unknown_captures: list[str] = []
    malformed: list[str] = []
    total_bytes = 0
    selected = 0
    scanned_times: list[datetime] = []
    for sequence in range(first, last + 1):
        census.check()
        index = document(root, f"by-sequence/{sequence:019d}")
        capture = str(UUID(str(index.get("capture_id"))))
        if index != dict(
            schema_version="capture-sequence-v1",
            store_id=str(control.store_id),
            capture_sequence=sequence,
            capture_id=capture,
        ):
            raise AuditError("sequence_index_mismatch")
        base = f"captures/{capture}"
        intent = Intent.model_validate(document(root, base + "/intent.json"))
        manifest_bytes = read_file(root, base + "/manifest.json")
        manifest = Manifest.model_validate_json(manifest_bytes)
        if (
            intent.capture_id != manifest.capture_id
            or str(intent.capture_id) != capture
            or intent.capture_sequence != sequence
            or manifest.completed_at < intent.requested_at
        ):
            raise AuditError("capture_identity_or_time_mismatch")
        receipt = manifest.receipt
        receipt_bytes = None
        if receipt is not None:
            receipt_bytes = read_file(root, base + "/response/receipt.json")
            if (
                Receipt.model_validate_json(receipt_bytes) != receipt
                or receipt.capture_id != intent.capture_id
                or receipt.requested_at != intent.requested_at
                or receipt.received_at < receipt.requested_at
                or receipt.received_at != manifest.completed_at
            ):
                raise AuditError("receipt_mismatch")
        at = receipt.received_at if receipt else intent.requested_at
        scanned_times.append(at)
        entry = [
            sequence,
            capture,
            digest(manifest_bytes),
            digest(receipt_bytes) if receipt_bytes else None,
            receipt.sha256 if receipt else None,
            manifest.outcome,
        ]
        inventory_hash.update(canonical(entry) + b"\n")
        inventory.append(entry)
        if not start <= at < end:
            continue
        selected += 1
        feed = feeds[intent.product]
        feed["selected"] += 1
        feed["outcomes"][manifest.outcome] += 1
        feed["modes"][intent.mode] += 1
        if receipt is None:
            continue
        total_bytes += receipt.byte_length
        if total_bytes > MAX_TOTAL_BYTES:
            raise AuditError("total_payload_limit")
        body = read_file(root, base + "/response/payload.bin", MAX_BYTES)
        if len(body) != receipt.byte_length or digest(body) != receipt.sha256:
            raise AuditError("payload_integrity_failure")
        feed["received"].append(receipt.received_at)
        parsed = gtfs.FeedMessage()
        try:
            parsed.ParseFromString(body)
            if not parsed.IsInitialized():
                raise DecodeError("missing_required_fields")
        except DecodeError:
            malformed.append(capture)
            continue
        feed["entities"] += len(parsed.entity)
        if census.inspect(parsed, intent.product + ":FeedMessage", capture):
            unknown_captures.append(capture)
    for feed in feeds.values():
        received = sorted(feed.pop("received"))
        points = [start, *received, end]
        feed["first_received_at"] = received[0].isoformat() if received else None
        feed["last_received_at"] = received[-1].isoformat() if received else None
        feed["max_receipt_gap_seconds_including_edges"] = max(
            (b - a).total_seconds() for a, b in zip(points, points[1:], strict=False)
        )
    # Sequence order is retained; clock rollback must not be hidden by sorted gaps.
    regressions = sum(b < a for a, b in zip(scanned_times, scanned_times[1:], strict=False))
    return dict(
        schema_version="tram-field-audit-v1",
        store_id=str(control.store_id),
        start=start.astimezone(UTC).isoformat(),
        end=end.astimezone(UTC).isoformat(),
        interval_seconds=(end - start).total_seconds(),
        first_sequence=first,
        last_sequence=last,
        high_water_sequence=high_water,
        scanned_captures=len(inventory),
        selected_captures=selected,
        payload_bytes=total_bytes,
        inventory_sha256=inventory_hash.hexdigest(),
        inventory=inventory,
        receipt_time_regressions=regressions,
        scanned_time_min=min(scanned_times).isoformat(),
        scanned_time_max=max(scanned_times).isoformat(),
        feeds=feeds,
        fields=census.report(),
        unknown_captures=unknown_captures,
        malformed_captures=malformed,
        descriptor_sha256=digest(gtfs.DESCRIPTOR.serialized_pb),
        schema_freeze_approved=False,
        mapping_completeness_evaluated=False,
        coverage_note=(
            "Only the explicit sequence range was scanned; interval length alone does not "
            "prove a full day. Review capture gaps, fixture/live modes "
            "and source-field dispositions."
        ),
    )


def provenance() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()

    files = [
        "scripts/tram_field_audit.py",
        "urbanpulse/contracts/capture_control.py",
        "urbanpulse/contracts/local_capture.py",
        "uv.lock",
    ]
    try:
        commit: str | None = git("rev-parse", "HEAD")
        dirty: bool | None = bool(git("status", "--porcelain"))
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return dict(
        commit=commit,
        dirty=dirty,
        files={name: digest((ROOT / name).read_bytes()) for name in files},
    )


def check_output_reserve(path: Path) -> None:
    ancestor = path.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < 5 * 1024**3 + 16 * 1024**2:
        raise AuditError("export_disk_reserve")
    if hasattr(os, "statvfs"):
        info = os.statvfs(ancestor)
        if info.f_favail < 100_010:
            raise AuditError("export_inode_reserve")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="New private directory outside store"
    )
    parser.add_argument("--start", required=True, help="Inclusive ISO time with offset")
    parser.add_argument("--end", required=True, help="Exclusive ISO time with offset")
    parser.add_argument("--first-sequence", type=int, default=1)
    parser.add_argument("--last-sequence", type=int)
    args = parser.parse_args()
    try:
        root, output = args.store.resolve(), args.output.resolve()
        if output.is_relative_to(root) or root.is_relative_to(output) or output.exists():
            raise AuditError("output_must_be_new_and_separate")
        check_output_reserve(output)
        report = audit(
            root,
            datetime.fromisoformat(args.start),
            datetime.fromisoformat(args.end),
            first=args.first_sequence,
            last=args.last_sequence,
        )
        report["audit_code"] = provenance()
        data = canonical(report)
        if len(data) > 16 * 1024**2:
            raise AuditError("report_size_limit")
        check_output_reserve(output)
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        temporary = output / "report.incomplete"
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.rename(output / "report.json")
        if os.name != "nt":
            descriptor = os.open(output, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        print("Audit report written; review required, no schema freeze or expiry authorized.")
        return 0
    except AuditError as error:
        print("Audit stopped: " + str(error))
    except (OSError, ValueError, KeyError, TypeError):
        print("Audit stopped: invalid or unavailable input/output")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
