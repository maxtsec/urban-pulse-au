"""Bounded static tram archive validation; never extract provider paths to disk."""

import base64
import csv
import hashlib
import io
import stat
import struct
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import httpx

from urbanpulse.application.schedule_archive import ArchiveError

SOURCE_URL = "https://opendata.transport.vic.gov.au/dataset/3f4e292e-7f8a-4ffe-831f-1953be0fe448/resource/fb152201-859f-4882-9206-b768060b50ad/download/gtfs.zip"
TRAM_MEMBER = "3/google_transit.zip"
REQUIRED = {"agency.txt", "routes.txt", "stops.txt", "trips.txt", "stop_times.txt", "shapes.txt"}
CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Limits:
    outer_bytes: int = 512 * 1024 * 1024
    tram_bytes: int = 128 * 1024 * 1024
    member_bytes: int = 512 * 1024 * 1024
    expanded_bytes: int = 1024 * 1024 * 1024
    entries: int = 256
    calendar_bytes: int = 8 * 1024 * 1024


def check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise ArchiveError("deadline_exceeded")


class Reader(Protocol):
    def read(self, size: int = -1) -> bytes: ...


def copy_bounded(source: Reader, target: BinaryIO, maximum: int, deadline: float) -> int:
    size = 0
    while True:
        check_deadline(deadline)
        chunk = source.read(CHUNK)
        if not chunk:
            return size
        size += len(chunk)
        if size > maximum:
            raise ArchiveError("expanded_size_exceeded")
        target.write(chunk)


def hashes(path: Path, deadline: float) -> dict[str, str | int]:
    sha, md5, size = hashlib.sha256(), hashlib.md5(usedforsecurity=False), 0
    with path.open("rb") as source:
        while chunk := source.read(CHUNK):
            check_deadline(deadline)
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    return {"size": size, "sha256": sha.hexdigest(), "md5": base64.b64encode(md5.digest()).decode()}


def check_zip_index(path: Path, limits: Limits) -> None:
    # Bound central-directory allocation before ZipFile constructs its entry objects.
    # The measured provider archives use ordinary single-disk ZIP, not ZIP64.
    size = path.stat().st_size
    with path.open("rb") as source:
        source.seek(max(0, size - 65557))
        tail = source.read(65557)
    at = tail.rfind(b"PK\x05\x06")
    if at < 0 or len(tail) - at < 22:
        raise ArchiveError("invalid_zip_index")
    _, disk, start_disk, disk_count, count, central_size, offset, comment = struct.unpack(
        "<4s4H2LH", tail[at : at + 22]
    )
    if (
        disk
        or start_disk
        or disk_count != count
        or count > limits.entries
        or central_size > 1024 * 1024
        or offset == 0xFFFFFFFF
        or at + 22 + comment != len(tail)
        or offset + central_size != size - len(tail) + at
    ):
        raise ArchiveError("unsupported_or_oversized_zip_index")


def safe_entries(archive: ZipFile, limits: Limits) -> None:
    entries = archive.infolist()
    if len(entries) > limits.entries:
        raise ArchiveError("too_many_zip_entries")
    names: set[str] = set()
    for entry in entries:
        name = entry.filename
        path = PurePosixPath(name)
        if (
            not name
            or name != entry.orig_filename
            or name in names
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or ":" in name
            or any(ord(c) < 32 for c in name)
            or name.rstrip("/") != str(path)
            or stat.S_ISLNK(entry.external_attr >> 16)
            or entry.flag_bits & 1
            or entry.compress_type not in (ZIP_DEFLATED, ZIP_STORED)
        ):
            raise ArchiveError("unsafe_zip_entry")
        names.add(name)


def download(
    client: httpx.Client, path: Path, deadline: float, limits: Limits
) -> dict[str, object]:
    size = 0
    with client.stream("GET", SOURCE_URL, headers={"Accept-Encoding": "identity"}) as response:
        if response.status_code != 200:
            raise ArchiveError("source_http_failure")
        if response.headers.get("content-encoding", "identity") != "identity":
            raise ArchiveError("unexpected_source_encoding")
        declared = response.headers.get("content-length")
        if declared is not None and (
            not declared.isdecimal() or int(declared) > limits.outer_bytes
        ):
            raise ArchiveError("download_size_exceeded")
        with path.open("xb") as output:
            for chunk in response.iter_raw(CHUNK):
                check_deadline(deadline)
                size += len(chunk)
                if size > limits.outer_bytes:
                    raise ArchiveError("download_size_exceeded")
                output.write(chunk)
        if declared is not None and size != int(declared):
            raise ArchiveError("incomplete_download")
        return {
            "source_url": SOURCE_URL,
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
        }


def calendar_summary(archive: ZipFile, limits: Limits, deadline: float) -> dict[str, object]:
    dates: list[str] = []
    counts: dict[str, int] = {}
    for name, fields in (
        ("calendar.txt", ("start_date", "end_date")),
        ("calendar_dates.txt", ("date",)),
    ):
        if name not in archive.namelist():
            continue
        if archive.getinfo(name).file_size > limits.calendar_bytes:
            raise ArchiveError("calendar_size_exceeded")
        with archive.open(name) as source:
            reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig", errors="strict"))
            if not reader.fieldnames or not set(fields) <= set(reader.fieldnames):
                raise ArchiveError("invalid_calendar_columns")
            count = 0
            for row in reader:
                check_deadline(deadline)
                count += 1
                if count > 100_000:
                    raise ArchiveError("calendar_rows_exceeded")
                for field in fields:
                    value = row[field]
                    if (
                        value is None
                        or len(value) != 8
                        or not value.isascii()
                        or not value.isdigit()
                    ):
                        raise ArchiveError("invalid_calendar_date")
                    datetime.strptime(value, "%Y%m%d")
                    dates.append(value)
            counts[name] = count
    return {
        "rows": counts,
        "date_min": min(dates, default=None),
        "date_max": max(dates, default=None),
        "service_applicability_verified": False,
    }


def prepare(
    outer: Path, destination: Path, deadline: float, limits: Limits | None = None
) -> dict[str, object]:
    limits = limits or Limits()
    if outer.stat().st_size > limits.outer_bytes:
        raise ArchiveError("download_size_exceeded")
    outer_hash = hashes(outer, deadline)
    check_zip_index(outer, limits)
    with ZipFile(outer) as archive:
        safe_entries(archive, limits)
        if TRAM_MEMBER not in archive.namelist():
            raise ArchiveError("tram_member_missing")
        if archive.getinfo(TRAM_MEMBER).file_size > limits.tram_bytes:
            raise ArchiveError("tram_size_exceeded")
        with archive.open(TRAM_MEMBER) as source, destination.open("xb") as output:
            copy_bounded(source, output, limits.tram_bytes, deadline)
    check_zip_index(destination, limits)
    with ZipFile(destination) as tram:
        safe_entries(tram, limits)
        names = set(tram.namelist())
        missing = sorted(REQUIRED - names)
        if not names.intersection({"calendar.txt", "calendar_dates.txt"}):
            missing.append("calendar.txt_or_calendar_dates.txt")
        if missing:
            raise ArchiveError("missing_required_files:" + ",".join(missing))
        if sum(x.file_size for x in tram.infolist()) > limits.expanded_bytes:
            raise ArchiveError("expanded_size_exceeded")
        members: list[dict[str, object]] = []
        for entry in tram.infolist():
            if entry.file_size > limits.member_bytes:
                raise ArchiveError("member_size_exceeded")
            sha = hashlib.sha256()
            size = 0
            with tram.open(entry) as source:
                while chunk := source.read(CHUNK):
                    check_deadline(deadline)
                    size += len(chunk)
                    if size > limits.member_bytes:
                        raise ArchiveError("member_size_exceeded")
                    sha.update(chunk)
            members.append({"name": entry.filename, "size": size, "sha256": sha.hexdigest()})
        calendar = calendar_summary(tram, limits, deadline)
    return {
        "outer": outer_hash,
        "tram": hashes(destination, deadline),
        "members": sorted(members, key=lambda x: str(x["name"])),
        "calendar": calendar,
    }
