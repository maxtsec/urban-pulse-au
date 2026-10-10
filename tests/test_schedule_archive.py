"""Archive identity, integrity, bounds and terminal publication without cloud credentials."""

import base64
import hashlib
import io
import json
import subprocess
import sys
import time
from dataclasses import replace
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import httpx
import pytest

from urbanpulse.adapters.gtfs_archive import (
    SOURCE_URL,
    TRAM_MEMBER,
    Limits,
    download,
    prepare,
)
from urbanpulse.adapters.gtfs_archive_gcs import GcsArchive
from urbanpulse.application.schedule_archive import PREFIX, ArchiveError, publish
from workers.schedule_archive.main import ArchiveRequest, execute, retained_provenance


def make_zip(entries, compression=ZIP_DEFLATED):
    target = io.BytesIO()
    with ZipFile(target, "w", compression=compression) as archive:
        for name, data in entries:
            if isinstance(name, str):
                entry = ZipInfo(name)
                entry.filename = name
                entry.orig_filename = name
                entry.compress_type = compression
            else:
                entry = name
            archive.writestr(entry, data)
    return target.getvalue()


def tram(extra=(), omit=()):
    entries = [
        (name + ".txt", "id\n1\n")
        for name in ("agency", "routes", "stops", "trips", "stop_times", "shapes")
    ]
    entries += [
        ("calendar.txt", "service_id,start_date,end_date\nx,20261001,20261231\n"),
        ("calendar_dates.txt", "service_id,date,exception_type\nx,20260101,1\n"),
    ]
    return make_zip([(n, d) for n, d in entries if n not in omit] + list(extra))


def fixture(tmp_path, body=None, outer_extra=()):
    body = tram() if body is None else body
    outer = tmp_path / "outer.zip"
    outer.write_bytes(make_zip([(TRAM_MEMBER, body), *outer_extra]))
    return outer


def deadline():
    return time.monotonic() + 60


def provenance(tmp_path, outer):
    with ZipFile(outer) as archive:
        member = archive.read(TRAM_MEMBER)
    path = tmp_path / "provenance.json"
    path.write_text(
        json.dumps(
            {
                "source_url": SOURCE_URL,
                "outer_sha256": hashlib.sha256(outer.read_bytes()).hexdigest(),
                "tram_sha256": hashlib.sha256(member).hexdigest(),
                "original_downloaded_at": None,
                "evidence_reference": "original/download.json",
            }
        )
    )
    return path


def test_exact_tram_bytes_calendar_and_bus_only_change(tmp_path):
    member = tram()
    outer = fixture(tmp_path, member, [("4/google_transit.zip", b"bus-a")])
    a = prepare(outer, tmp_path / "a.zip", deadline())
    outer.write_bytes(make_zip([(TRAM_MEMBER, member), ("4/google_transit.zip", b"bus-b")]))
    b = prepare(outer, tmp_path / "b.zip", deadline())
    assert a["outer"]["sha256"] != b["outer"]["sha256"]
    assert a["tram"] == b["tram"]
    assert (tmp_path / "a.zip").read_bytes() == member
    assert a["calendar"]["date_min"] == "20260101"
    assert a["calendar"]["date_max"] == "20261231"
    assert a["calendar"]["service_applicability_verified"] is False


@pytest.mark.parametrize(
    "name", ["../bad", "/bad", "a/../bad", "a\\bad", "C:bad", "a//bad", "a/./bad"]
)
@pytest.mark.parametrize("level", ["inner", "outer"])
def test_unsafe_zip_paths(tmp_path, name, level):
    outer = fixture(
        tmp_path,
        tram(extra=[(name, b"bad")]) if level == "inner" else None,
        [(name, b"bad")] if level == "outer" else (),
    )
    with pytest.raises(ArchiveError, match="unsafe_zip_entry"):
        prepare(outer, tmp_path / "tram.zip", deadline())
    assert not (tmp_path.parent / "bad").exists()


def test_duplicate_and_symlink_entries(tmp_path):
    with pytest.warns(UserWarning):
        body = tram(extra=[("routes.txt", b"again")])
    outer = fixture(tmp_path, body)
    with pytest.raises(ArchiveError, match="unsafe_zip_entry"):
        prepare(outer, tmp_path / "duplicate.zip", deadline())
    entry = ZipInfo("shortcut")
    entry.create_system = 3
    entry.external_attr = 0o120777 << 16
    outer.write_bytes(make_zip([(TRAM_MEMBER, tram(extra=[(entry, b"target")]))]))
    with pytest.raises(ArchiveError, match="unsafe_zip_entry"):
        prepare(outer, tmp_path / "symlink.zip", deadline())


@pytest.mark.parametrize("omit", [("trips.txt",), ("calendar.txt", "calendar_dates.txt")])
def test_required_member_absence(tmp_path, omit):
    with pytest.raises(ArchiveError, match="missing_required_files"):
        prepare(fixture(tmp_path, tram(omit=omit)), tmp_path / "tram.zip", deadline())


@pytest.mark.parametrize(
    "field,value",
    [
        ("outer_bytes", 10),
        ("tram_bytes", 10),
        ("member_bytes", 10),
        ("expanded_bytes", 10),
        ("entries", 1),
        ("calendar_bytes", 1),
    ],
)
def test_bounds(tmp_path, field, value):
    with pytest.raises(ArchiveError):
        prepare(
            fixture(tmp_path),
            tmp_path / "tram.zip",
            deadline(),
            replace(Limits(), **{field: value}),
        )


def test_crc_and_deadline(tmp_path):
    member = make_zip([("routes.txt", b"unique-body-for-crc")], compression=ZIP_STORED)
    broken = member.replace(b"unique-body-for-crc", b"unique-BODY-for-crc")
    outer = fixture(tmp_path, broken)
    # Outer CRC succeeds; inner data must still be validated (use otherwise valid inner ZIP).
    valid = tram()
    with ZipFile(io.BytesIO(valid)) as z:
        entries = [(i.filename, z.read(i)) for i in z.infolist()]
    stored = make_zip(entries, ZIP_STORED).replace(
        b"service_id,start_date", b"Service_id,start_date", 1
    )
    outer.write_bytes(make_zip([(TRAM_MEMBER, stored)]))
    from zipfile import BadZipFile

    with pytest.raises(BadZipFile):
        prepare(outer, tmp_path / "bad.zip", deadline())
    with pytest.raises(ArchiveError, match="deadline_exceeded"):
        prepare(outer, tmp_path / "expired.zip", time.monotonic() - 1)


@pytest.mark.parametrize(
    "status,headers,body,limit",
    [
        (302, {"location": "https://untrusted.test"}, b"", 100),
        (200, {"content-encoding": "gzip"}, b"", 100),
        (200, {"content-length": "200"}, b"", 100),
        (200, {"content-length": "5"}, b"abc", 100),
        (200, {}, b"abcd", 3),
    ],
)
def test_download_refusals(tmp_path, status, headers, body, limit):
    calls = []

    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(status, headers=headers, stream=httpx.ByteStream(body))

    with httpx.Client(transport=httpx.MockTransport(handle), follow_redirects=False) as client:
        with pytest.raises(ArchiveError):
            download(
                client, tmp_path / "download.zip", deadline(), replace(Limits(), outer_bytes=limit)
            )
    assert calls == [SOURCE_URL]


class ObjectServer:
    def __init__(self):
        self.values = {}
        self.calls = []
        self.behavior = None

    def handle(self, request):
        self.calls.append(request)
        from urllib.parse import unquote

        name = (
            request.url.params.get("name")
            if request.method == "POST"
            else unquote(request.url.path.split("/o/")[1])
        )
        if request.method == "GET":
            assert "alt" not in request.url.params
            return (
                httpx.Response(200, json=self.values[name])
                if name in self.values
                else httpx.Response(404)
            )
        assert request.method == "POST"
        assert request.url.params["ifGenerationMatch"] == "0"
        data = request.read()
        md5 = base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode()
        assert request.headers["X-Goog-Hash"] == "md5=" + md5
        value = {
            "name": name,
            "bucket": "archive-test",
            "generation": "123",
            "size": str(len(data)),
            "md5Hash": md5,
        }
        self.values[name] = value
        if self.behavior == "lost_ack":
            raise httpx.ReadError("redacted transport error")
        if self.behavior == "race":
            return httpx.Response(412)
        return httpx.Response(200, json=value)


@pytest.mark.parametrize("behavior", [None, "lost_ack", "race"])
def test_gcs_create_and_reconcile(tmp_path, behavior):
    path = tmp_path / "body"
    path.write_bytes(b"tram archive bytes")
    server = ObjectServer()
    server.behavior = behavior
    with httpx.Client(transport=httpx.MockTransport(server.handle)) as client:
        objects = GcsArchive("archive-test", lambda: "test-token", deadline(), client)
        first = objects.confirm(PREFIX + "objects/example", path)
        second = objects.confirm(PREFIX + "objects/example", path)
    assert first["generation"] == second["generation"] == "123"
    assert first["outcome"] == ("created" if behavior is None else "reconciled")
    assert second["outcome"] == "existing"
    assert sum(r.method == "POST" for r in server.calls) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("md5Hash", "wrong"),
        ("size", "999"),
        ("generation", None),
        ("generation", "0"),
        ("componentCount", 2),
        ("bucket", "wrong"),
        ("name", "wrong"),
    ],
)
def test_gcs_conflict_never_overwrites(tmp_path, field, value):
    path = tmp_path / "body"
    path.write_bytes(b"valid")
    server = ObjectServer()
    with httpx.Client(transport=httpx.MockTransport(server.handle)) as client:
        objects = GcsArchive("archive-test", lambda: "test", deadline(), client)
        objects.confirm(PREFIX + "objects/example", path)
        server.values[PREFIX + "objects/example"][field] = value
        with pytest.raises(ArchiveError, match="gcs_object_conflict"):
            objects.confirm(PREFIX + "objects/example", path)
    assert sum(r.method == "POST" for r in server.calls) == 1


def test_gcs_wrong_prefix_and_denial(tmp_path):
    path = tmp_path / "body"
    path.write_bytes(b"data")

    def denied(request):
        return httpx.Response(403, text="never expose this body")

    with httpx.Client(transport=httpx.MockTransport(denied)) as client:
        objects = GcsArchive("archive-test", lambda: "test", deadline(), client)
        with pytest.raises(ValueError, match="outside"):
            objects.confirm("raw/tram/body", path)
        with pytest.raises(ArchiveError, match="^gcs_unconfirmed$"):
            objects.confirm(PREFIX + "body", path)


class MemoryObjects:
    def __init__(self):
        self.content = {}
        self.fail = None

    def confirm(self, name, path):
        if name.endswith(str(self.fail)):
            raise RuntimeError("storage failure")
        data = path.read_bytes()
        existed = name in self.content
        if existed and self.content[name] != data:
            raise RuntimeError("conflict")
        self.content[name] = data
        return {"name": name, "generation": "7", "outcome": "existing" if existed else "created"}


def test_publication_unchanged_receipt_and_changed_archive(tmp_path):
    objects = MemoryObjects()
    outcomes = []
    for n, payload in enumerate([b"same", b"same", b"changed"]):
        work = tmp_path / str(n)
        work.mkdir()
        (work / "tram.zip").write_bytes(payload)

        def acquire(payload=payload):
            assert any(k.endswith("incomplete.json") for k in objects.content)
            return {"tram": {"sha256": hashlib.sha256(payload).hexdigest()}}, {
                "original_downloaded_at": None
            }

        outcomes.append(
            publish(objects, work, acquire, code_version="abc", mode="seed")["archive_outcome"]
        )
    assert outcomes == ["created", "existing", "created"]
    assert sum(k.endswith("tram.zip") for k in objects.content) == 2
    assert sum(k.endswith("manifest.json") for k in objects.content) == 3


@pytest.mark.parametrize(
    "failure", ["acquire", "tram.zip", "manifest.json", "attempt.json", "incomplete.json"]
)
def test_failed_publication_never_success(tmp_path, failure):
    objects = MemoryObjects()
    objects.fail = failure
    (tmp_path / "tram.zip").write_bytes(b"test")
    called = []

    def acquire():
        called.append(True)
        if failure == "acquire":
            raise ArchiveError("source_http_failure")
        return {"tram": {"sha256": "a" * 64}}, {}

    with pytest.raises((RuntimeError, ArchiveError)):
        publish(objects, tmp_path, acquire, code_version="abc", mode="check")
    if failure in ("attempt.json", "incomplete.json"):
        assert not called
    manifests = [json.loads(v) for k, v in objects.content.items() if k.endswith("manifest.json")]
    assert all(m["status"] == "incomplete" for m in manifests)


def test_readonly_inspection_unknown_original_timestamp(tmp_path, monkeypatch):
    outer = fixture(tmp_path)
    record = provenance(tmp_path, outer)
    before = outer.read_bytes()

    def no_auth(*args, **kwargs):
        pytest.fail("offline inspection attempted cloud authentication")

    monkeypatch.setattr("urbanpulse.adapters.gtfs_archive_auth.compute_engine.Credentials", no_auth)
    request = ArchiveRequest(
        "inspect", None, None, "test", str(outer), str(record), str(tmp_path / "report")
    )
    result = execute(request, deadline())
    report = json.loads((tmp_path / "report/report.json").read_text())
    assert result["kind"] == "gtfs_archive_inspection"
    assert report["provenance"]["original_downloaded_at"] is None
    assert report["provenance"]["download_time_unknown"]
    assert outer.read_bytes() == before
    with pytest.raises(FileExistsError):
        execute(request, deadline())
    value = json.loads(record.read_text())
    value["tram_sha256"] = "0" * 64
    record.write_text(json.dumps(value))
    with pytest.raises(ArchiveError, match="retained_source_hash_mismatch"):
        execute(replace(request, output=str(tmp_path / "other")), deadline())
    assert not (tmp_path / "other").exists()


def test_wrong_runtime_identity_before_any_writes(tmp_path, monkeypatch):
    class Credentials:
        service_account_email = "deployer@project.iam.gserviceaccount.com"

        def refresh(self, request):
            pass

    monkeypatch.setattr(
        "urbanpulse.adapters.gtfs_archive_auth.compute_engine.Credentials", Credentials
    )
    request = ArchiveRequest(
        "check", "archive-test", "archive@project.iam.gserviceaccount.com", "test"
    )
    with pytest.raises(ValueError, match="unexpected runtime identity"):
        execute(request, deadline())


@pytest.mark.parametrize("date", ["2026-10-01T00:00:00", "2099-01-01T00:00:00Z", "garbage"])
def test_invalid_download_timestamp(tmp_path, date):
    outer = fixture(tmp_path)
    path = provenance(tmp_path, outer)
    value = json.loads(path.read_text())
    value["original_downloaded_at"] = date
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        retained_provenance(path)


def test_real_cli_offline(tmp_path):
    outer = fixture(tmp_path)
    record = provenance(tmp_path, outer)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "workers.schedule_archive.main",
            "inspect",
            "--source-zip",
            str(outer),
            "--provenance",
            str(record),
            "--output",
            str(tmp_path / "cli"),
            "--code-version",
            "test",
            "--timeout-seconds",
            "30",
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [json.loads(x) for x in result.stdout.splitlines()]
    assert lines[-1]["kind"] == "gtfs_archive_inspection"
    assert (tmp_path / "cli/report.json").exists()


def test_seed_not_a_daily_success_and_rollback_clock(tmp_path):
    objects = MemoryObjects()
    (tmp_path / "tram.zip").write_bytes(b"test")
    dates = iter(["2026-10-10T01:00:00Z", "2026-10-10T00:59:00Z"])
    result = publish(
        objects,
        tmp_path,
        lambda: ({"tram": {"sha256": "a" * 64}}, {}),
        code_version="test",
        mode="seed",
        now=lambda: next(dates),
    )
    assert result["kind"] == "gtfs_archive_seeded"
    assert result["completed_at"] == "2026-10-10T01:00:00Z"
    manifest = json.loads(
        next(v for k, v in objects.content.items() if k.endswith("manifest.json"))
    )
    assert manifest["completed_at"] == result["completed_at"]


def test_unconfirmed_final_manifest_stays_pending(tmp_path):
    class LostManifest(MemoryObjects):
        def confirm(self, name, path):
            result = super().confirm(name, path)
            if name.endswith("manifest.json"):
                raise RuntimeError("lost response")
            return result

    objects = LostManifest()
    (tmp_path / "tram.zip").write_bytes(b"test")
    with pytest.raises(RuntimeError):
        publish(
            objects,
            tmp_path,
            lambda: ({"tram": {"sha256": "a" * 64}}, {}),
            code_version="test",
            mode="check",
        )
    # No competing incomplete terminal write overwrites an already stored complete manifest.
    manifests = [json.loads(v) for k, v in objects.content.items() if k.endswith("manifest.json")]
    assert len(manifests) == 1 and manifests[0]["status"] == "complete"


def test_interrupt_leaves_no_complete_manifest(tmp_path):
    objects = MemoryObjects()

    def interrupt():
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        publish(objects, tmp_path, interrupt, code_version="test", mode="check")
    assert len(objects.content) == 2
    assert not any(k.endswith("manifest.json") for k in objects.content)


def test_gcs_oversized_metadata_and_missing_after_lost_ack(tmp_path):
    path = tmp_path / "data"
    path.write_bytes(b"test")
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 65537))
    ) as client:
        with pytest.raises(ArchiveError, match="gcs_metadata_too_large"):
            GcsArchive("archive-test", lambda: "test", deadline(), client).confirm(
                PREFIX + "data", path
            )
    calls = []

    def failed(request):
        calls.append(request.method)
        if request.method == "POST":
            raise httpx.ReadError("lost acknowledgement")
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(failed)) as client:
        with pytest.raises(ArchiveError, match="gcs_unconfirmed"):
            GcsArchive("archive-test", lambda: "test", deadline(), client).confirm(
                PREFIX + "data", path
            )
    assert calls == ["GET", "POST", "GET"]
