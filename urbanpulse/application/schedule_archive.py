"""Publish immutable static archives and per-check receipts through narrow ports."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

PREFIX = "static/gtfs-tram/"
FORMAT = "gtfs-tram-archive-v1"


class ArchiveError(ValueError):
    """Fixed operational reason, excluding provider bodies and credentials."""


class Objects(Protocol):
    def confirm(self, name: str, path: Path) -> dict[str, object]:
        """Create or checksum-confirm an exact known object; never list or overwrite."""
        ...


def timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def publish(
    objects: Objects,
    workspace: Path,
    acquire: Callable[[], tuple[dict[str, object], dict[str, object]]],
    *,
    code_version: str,
    mode: str,
    now: Callable[[], str] = timestamp,
) -> dict[str, str]:
    started = now()
    check_id = uuid4().hex
    root = f"{PREFIX}checks/date={started[:10]}/{check_id}/"

    def document(name: str, value: dict[str, object]) -> dict[str, object]:
        path = workspace / name
        with path.open("xb") as output:
            output.write(
                json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            )
        return objects.confirm(root + name, path)

    base: dict[str, object] = {
        "format": FORMAT,
        "check_id": check_id,
        "started_at": started,
        "code_version": code_version,
        "mode": mode,
    }
    document("attempt.json", base)
    document("incomplete.json", {**base, "status": "pending"})
    try:
        inventory, provenance = acquire()
        tram = inventory["tram"]
        if not isinstance(tram, dict) or not isinstance(tram.get("sha256"), str):
            raise ValueError("invalid archive inventory")
        archive_ref = objects.confirm(
            PREFIX + "objects/sha256=" + tram["sha256"] + "/tram.zip", workspace / "tram.zip"
        )
    except Exception as error:
        reason = (
            str(error) if isinstance(error, ArchiveError) else "acquisition_or_publication_failed"
        )
        # An interrupted process may leave only the initial marker; neither is success.
        try:
            document(
                "manifest.json",
                {
                    **base,
                    "status": "incomplete",
                    "reason": reason,
                    "completed_at": max(started, now()),
                },
            )
        except Exception:
            pass
        raise
    # Never attempt a second terminal result after a lost manifest acknowledgement.
    completed = max(started, now())
    manifest = document(
        "manifest.json",
        {
            **base,
            "status": "complete",
            "provenance": provenance,
            "inventory": inventory,
            "archive": archive_ref,
            "completed_at": completed,
            "attribution": (
                "Department of Transport and Planning, Victoria; GTFS Schedule; "
                "CC BY 4.0. Exact tram member retained; other modes excluded."
            ),
        },
    )
    return {
        "status": "complete",
        "kind": "gtfs_archive_success" if mode == "check" else "gtfs_archive_seeded",
        "completed_at": completed,
        "code_version": code_version,
        "check_id": check_id,
        "manifest": str(manifest["name"]),
        "generation": str(manifest["generation"]),
        "tram_sha256": tram["sha256"],
        "archive_outcome": str(archive_ref["outcome"]),
    }
