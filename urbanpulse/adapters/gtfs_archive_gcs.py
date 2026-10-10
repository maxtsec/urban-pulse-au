"""Prefix-limited create/get via single-request uploads and server MD5 metadata."""

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import quote

import httpx

from urbanpulse.adapters.gtfs_archive import CHUNK, check_deadline, hashes
from urbanpulse.application.schedule_archive import PREFIX, ArchiveError


class GcsArchive:
    def __init__(
        self, bucket: str, token: Callable[[], str], deadline: float, client: httpx.Client
    ):
        if re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,220}[a-z0-9]", bucket) is None:
            raise ValueError("invalid bucket")
        self.bucket, self.token, self.deadline, self.client = bucket, token, deadline, client

    def request(
        self,
        method: str,
        url: str,
        *,
        body: Iterator[bytes] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        check_deadline(self.deadline)
        auth = {"Authorization": "Bearer " + self.token(), **(headers or {})}
        with self.client.stream(method, url, headers=auth, content=body) as response:
            payload = bytearray()
            for chunk in response.iter_bytes(16384):
                check_deadline(self.deadline)
                payload.extend(chunk)
                if len(payload) > 65536:
                    raise ArchiveError("gcs_metadata_too_large")
            if response.status_code not in (200, 201):
                return response.status_code, {}
            value = json.loads(payload)
            if not isinstance(value, dict):
                raise ArchiveError("gcs_metadata_invalid")
            return response.status_code, value

    def confirm(self, name: str, path: Path) -> dict[str, object]:
        if not name.startswith(PREFIX) or ".." in name or "\\" in name:
            raise ValueError("outside static archive prefix")
        local = hashes(path, self.deadline)
        # Includes manifests; independent caller/ZIP bounds are stricter where appropriate.
        if int(local["size"]) > 128 * 1024 * 1024:
            raise ArchiveError("gcs_upload_too_large")
        metadata_url = (
            f"https://storage.googleapis.com/storage/v1/b/{self.bucket}/o/{quote(name, safe='')}"
        )
        status, metadata = self.request("GET", metadata_url)
        outcome = "existing"
        if status == 404:

            def content() -> Iterator[bytes]:
                with path.open("rb") as source:
                    while chunk := source.read(CHUNK):
                        check_deadline(self.deadline)
                        yield chunk

            upload_url = (
                f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o"
                f"?uploadType=media&ifGenerationMatch=0&name={quote(name, safe='')}"
            )
            try:
                status, metadata = self.request(
                    "POST",
                    upload_url,
                    body=content(),
                    headers={
                        "Content-Length": str(local["size"]),
                        "X-Goog-Hash": "md5=" + str(local["md5"]),
                        "Content-Type": "application/zip"
                        if name.endswith(".zip")
                        else "application/json",
                    },
                )
            except httpx.TransportError:
                # The acknowledgement may have been lost after commit. Never repeat the write.
                status, metadata = self.request("GET", metadata_url)
                outcome = "reconciled"
            else:
                if status == 412 or status >= 500 or status == 429:
                    status, metadata = self.request("GET", metadata_url)
                    outcome = "reconciled"
                else:
                    outcome = "created"
        if status not in (200, 201):
            raise ArchiveError("gcs_unconfirmed")
        generation = metadata.get("generation")
        if (
            metadata.get("bucket") != self.bucket
            or metadata.get("name") != name
            or metadata.get("size") != str(local["size"])
            or metadata.get("md5Hash") != local["md5"]
            or metadata.get("componentCount") is not None
            or not isinstance(generation, str)
            or not generation.isdecimal()
            or int(generation) < 1
        ):
            raise ArchiveError("gcs_object_conflict")
        return {"name": name, "generation": generation, **local, "outcome": outcome}
