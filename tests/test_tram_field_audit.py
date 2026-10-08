"""Offline audit behavior against immutable synthetic v3 captures."""

import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from google.transit import gtfs_realtime_pb2 as gtfs

from scripts import tram_field_audit as tool
from urbanpulse.contracts.capture_control import Control, Summary, canonical
from urbanpulse.contracts.local_capture import Intent, Manifest, Receipt

START = datetime(2026, 10, 8, tzinfo=UTC)
END = START + timedelta(days=1)


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes([value]))


def payload(*, unknown=False, enum=False):
    message = gtfs.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    for number in range(2):
        entity = message.entity.add(id=f"vehicle-{number}")
        entity.vehicle.vehicle.id = "private-value-not-in-report"
        entity.vehicle.position.latitude = -37.82
        entity.vehicle.position.longitude = 144.96
        if number == 0:
            entity.vehicle.position.speed = 0
        if unknown:
            entity.vehicle.ParseFromString(
                entity.vehicle.SerializeToString() + varint(1001 << 3) + varint(1)
            )
        if enum:
            entity.vehicle.ParseFromString(
                entity.vehicle.SerializeToString() + varint(9 << 3) + varint(999)
            )
    return message.SerializeToString()


def build_store(tmp_path, bodies=None, times=None, pending=False):
    root = tmp_path / "raw"
    root.mkdir()
    for directory in ("expiry", "policies", "captures", "by-sequence"):
        (root / directory).mkdir()
    store_id = uuid4()
    (root / "store.json").write_bytes(
        canonical(dict(schema_version="capture-store-v3", store_id=str(store_id)))
    )
    bodies = [payload()] if bodies is None else bodies
    times = (
        [START + timedelta(seconds=60 * (i + 1)) for i in range(len(bodies))]
        if times is None
        else times
    )
    summary = Summary()
    for sequence, (body, at) in enumerate(zip(bodies, times, strict=True), 1):
        identity = uuid4()
        intent = Intent(
            capture_id=identity,
            capture_sequence=sequence,
            mode="fixture",
            provider="synthetic",
            product="vehicle-positions",
            requested_at=at - timedelta(seconds=1),
            collector_version="test",
        )
        receipt = (
            None
            if body is None
            else Receipt(
                capture_id=identity,
                requested_at=intent.requested_at,
                received_at=at,
                byte_length=len(body),
                sha256=hashlib.sha256(body).hexdigest(),
            )
        )
        manifest = Manifest(
            capture_id=identity,
            outcome="captured" if body is not None else "fetch-failed",
            completed_at=at,
            receipt=receipt,
            http_status=200 if body is not None else 503,
            reason=None if body is not None else "http_error",
        )
        directory = root / "captures" / str(identity)
        directory.mkdir()
        (directory / "intent.json").write_text(intent.model_dump_json(), encoding="utf-8")
        (directory / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
        if receipt:
            (directory / "response").mkdir()
            (directory / "response/receipt.json").write_text(
                receipt.model_dump_json(), encoding="utf-8"
            )
            (directory / "response/payload.bin").write_bytes(body)
        (root / "by-sequence" / f"{sequence:019d}").write_bytes(
            canonical(
                dict(
                    schema_version="capture-sequence-v1",
                    store_id=str(store_id),
                    capture_sequence=sequence,
                    capture_id=str(identity),
                )
            )
        )
        summary = summary.include(intent, manifest)
    next_sequence = len(bodies) + 1
    pending_intent = (
        Intent(
            capture_id=uuid4(),
            capture_sequence=next_sequence,
            mode="fixture",
            provider="synthetic",
            product="trip-updates",
            requested_at=END,
            collector_version="test",
        )
        if pending
        else None
    )
    control = Control(
        store_id=store_id,
        generation=2 * len(bodies) + int(pending),
        next_capture_sequence=next_sequence + int(pending),
        pending=pending_intent,
        summary=summary,
    )
    (root / "control.json").write_bytes(canonical(control.document()))
    return root


def fingerprint(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_replay_counts_presence_without_values_and_never_writes(tmp_path):
    root = build_store(tmp_path, [payload(), payload()])
    before = fingerprint(root)
    report = tool.audit(root, START, END)
    again = tool.audit(root, START, END)
    assert report == again
    assert before == fingerprint(root)
    field = next(v for k, v in report["fields"].items() if k.endswith(".speed#5"))
    assert (field["present"], field["absent"], field["explicit_default"]) == (2, 2, 2)
    assert field["captures_present"] == 2
    assert "private-value-not-in-report" not in json.dumps(report)
    assert report["schema_freeze_approved"] is False
    assert report["mapping_completeness_evaluated"] is False
    assert report["selected_captures"] == 2
    assert report["feeds"]["vehicle-positions"]["entities"] == 4
    assert (
        report["inventory_sha256"]
        == hashlib.sha256(
            b"".join(canonical(row) + b"\n" for row in report["inventory"])
        ).hexdigest()
    )


@pytest.mark.parametrize("kind", ["unknown", "enum"])
def test_unknown_nested_fields_are_not_discarded(tmp_path, kind):
    root = build_store(tmp_path, [payload(**{kind: True})])
    report = tool.audit(root, START, END)
    assert len(report["unknown_captures"]) == 1
    rows = [v for v in report["fields"].values() if v["kind"].startswith("unknown")]
    assert len(rows) == 1
    assert rows[0]["present"] == 2
    assert rows[0]["captures_present"] == 1


def test_pending_without_files_is_excluded(tmp_path):
    root = build_store(tmp_path, pending=True)
    report = tool.audit(root, START, END)
    assert report["high_water_sequence"] == 1
    with pytest.raises(tool.AuditError, match="sequence_range"):
        tool.audit(root, START, END, last=2)


def test_half_open_interval_failures_and_clock_rollback(tmp_path):
    root = build_store(
        tmp_path,
        [payload(), payload(), None, payload()],
        [START, END, START + timedelta(hours=1), START + timedelta(minutes=30)],
    )
    report = tool.audit(root, START, END)
    assert report["selected_captures"] == 3
    assert report["receipt_time_regressions"] == 2
    assert report["feeds"]["vehicle-positions"]["outcomes"]["fetch-failed"] == 1
    assert report["feeds"]["trip-updates"]["max_receipt_gap_seconds_including_edges"] == 86400


def test_malformed_protobuf_is_explicit(tmp_path):
    root = build_store(tmp_path, [b"\xff", payload()])
    report = tool.audit(root, START, END)
    assert len(report["malformed_captures"]) == 1
    assert report["selected_captures"] == 2


@pytest.mark.parametrize(
    "target", ["payload", "index", "checksum", "receipt", "manifest", "expiry", "policies"]
)
def test_invalid_input_fails_without_modifying_store(tmp_path, target):
    root = build_store(tmp_path)
    capture = next((root / "captures").iterdir())
    if target == "payload":
        (capture / "response/payload.bin").write_bytes(b"wrong")
    elif target == "index":
        (root / "by-sequence/0000000000000000001").write_text("{}")
    elif target == "checksum":
        data = json.loads((root / "control.json").read_bytes())
        data["checksum"] = "bad"
        (root / "control.json").write_text(json.dumps(data))
    elif target == "receipt":
        data = json.loads((capture / "response/receipt.json").read_bytes())
        data["sha256"] = "0" * 64
        (capture / "response/receipt.json").write_text(json.dumps(data))
    elif target == "manifest":
        (capture / "manifest.json").unlink()
    else:
        (root / target / "record.json").write_text("{}")
    before = fingerprint(root)
    with pytest.raises((ValueError, OSError)):
        tool.audit(root, START, END)
    assert fingerprint(root) == before


@pytest.mark.parametrize(
    "bound,value",
    [
        ("MAX_CAPTURES", 0),
        ("MAX_TOTAL_BYTES", 0),
        ("MAX_FIELDS", 1),
        ("MAX_VISITS", 1),
        ("MAX_SECONDS", 0),
    ],
)
def test_bounds_fail_without_partial_success(tmp_path, monkeypatch, bound, value):
    root = build_store(tmp_path)
    monkeypatch.setattr(tool, bound, value)
    with pytest.raises(tool.AuditError):
        tool.audit(root, START, END)


def test_cli_new_external_output_and_no_network(tmp_path, monkeypatch):
    import socket

    root = build_store(tmp_path)
    before = fingerprint(root)
    output = tmp_path / "private-report"
    monkeypatch.setattr(
        socket, "create_connection", lambda *a, **k: pytest.fail("network forbidden")
    )
    monkeypatch.setattr(tool, "check_output_reserve", lambda _: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit",
            "--store",
            str(root),
            "--output",
            str(output),
            "--start",
            START.isoformat(),
            "--end",
            END.isoformat(),
        ],
    )
    assert tool.main() == 0
    report = json.loads((output / "report.json").read_bytes())
    assert report["audit_code"]["files"]
    assert tool.main() == 2  # Never replace prior evidence.
    assert fingerprint(root) == before
    assert not (output / "report.incomplete").exists()


def test_cli_output_in_store_rejected_before_reading(tmp_path, monkeypatch):
    root = build_store(tmp_path)
    monkeypatch.setattr(tool, "audit", lambda *a, **kw: pytest.fail("must refuse first"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit",
            "--store",
            str(root),
            "--output",
            str(root / "report"),
            "--start",
            START.isoformat(),
            "--end",
            END.isoformat(),
        ],
    )
    assert tool.main() == 2
    assert not (root / "report").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux lock and read-only mode")
def test_runs_with_collector_lock_held_and_read_only_tree(tmp_path):
    import fcntl

    root = build_store(tmp_path)
    lock = root / ".collector.lock"
    lock.touch()
    before = fingerprint(root)
    with lock.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        paths = list(root.rglob("*"))
        try:
            for path in paths:
                path.chmod(0o500 if path.is_dir() else 0o400)
            root.chmod(0o500)
            assert tool.audit(root, START, END)["selected_captures"] == 1
            assert fingerprint(root) == before
        finally:
            root.chmod(0o700)
            for path in paths:
                path.chmod(0o700 if path.is_dir() else 0o600)


@pytest.mark.skipif(sys.platform != "linux", reason="Unprivileged symlinks")
def test_symlink_input_rejected(tmp_path):
    root = build_store(tmp_path)
    payload_file = next((root / "captures").glob("*/response/payload.bin"))
    saved = tmp_path / "outside.bin"
    payload_file.rename(saved)
    payload_file.symlink_to(saved)
    with pytest.raises(tool.AuditError, match="path_escape|symlink"):
        tool.audit(root, START, END)


def test_output_reserve_stops_before_scan(tmp_path, monkeypatch):
    from collections import namedtuple

    root = build_store(tmp_path)
    output = tmp_path / "report"
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(tool.shutil, "disk_usage", lambda _: usage(100, 100, 0))
    monkeypatch.setattr(tool, "audit", lambda *a, **kw: pytest.fail("reserve must stop first"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit",
            "--store",
            str(root),
            "--output",
            str(output),
            "--start",
            START.isoformat(),
            "--end",
            END.isoformat(),
        ],
    )
    assert tool.main() == 2
    assert not output.exists()


def test_requested_subrange_never_reads_old_payloads(tmp_path):
    root = build_store(tmp_path, [payload(), payload()])
    first_id = json.loads((root / "by-sequence/0000000000000000001").read_bytes())["capture_id"]
    (root / "captures" / first_id / "response/payload.bin").unlink()
    report = tool.audit(root, START, END, first=2, last=2)
    assert report["scanned_captures"] == 1
    assert report["first_sequence"] == 2
    assert report["mapping_completeness_evaluated"] is False
