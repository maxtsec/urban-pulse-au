"""Build an offline, order-independent content-addressed pool of complete tram shapes."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from scripts.build_tram_fixture import ARCHIVE_SHA256, ROOT, TRAM_SHA256, encoded

INDEX = ROOT / "tests/fixtures/map02-expansion/index.json"
POLICY = "full-shape-content-v1"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_inputs(index: dict, root: Path) -> dict[str, dict]:
    """Validate the retained fixture inputs; never use area-owned files as serving units."""
    if index["schema_version"] != "map02-area-shapes-v1":
        raise ValueError("Unsupported area index")
    if (
        index["source_archive_sha256"] != ARCHIVE_SHA256
        or index["tram_archive_sha256"] != TRAM_SHA256
    ):
        raise ValueError("Source release is not the pinned foundation")
    features = {}
    for name, asset in index["assets"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Asset path escapes input root")
        raw = path.read_bytes()
        if len(raw) != asset["bytes"] or digest(raw) != asset["sha256"]:
            raise ValueError("Asset integrity check failed")
        content = json.loads(raw)
        identities = []
        for feature in content["features"]:
            identity = feature["properties"]["shape_id"]
            if identity in features:
                raise ValueError("Duplicate shape identity")
            features[identity] = feature
            identities.append(identity)
        if sorted(identities) != asset["shape_ids"]:
            raise ValueError("Asset shape list differs")
    for area in index["areas"].values():
        path = (root / area["boundary_path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Boundary path escapes input root")
        raw = path.read_bytes().replace(b"\r\n", b"\n")
        if digest(raw) != area["boundary_sha256"]:
            raise ValueError("Boundary integrity check failed")
        if json.loads(raw)["properties"]["name"] != area["name"]:
            raise ValueError("Boundary name differs")
    return features


def build_pool(index: dict, features: dict[str, dict]) -> tuple[dict[str, bytes], dict]:
    """Per-shape identity excludes geographic ownership and input registration order."""
    source = {
        key: index[key]
        for key in (
            "source_archive_sha256",
            "tram_archive_sha256",
            "source_url",
            "source_last_modified",
            "licence",
            "licence_url",
            "attribution",
            "selection_policy",
        )
    }
    files: dict[str, bytes] = {}
    objects = {}
    area_records = {}
    for area_id, area in sorted(index["areas"].items()):
        ids = area["shape_ids"]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate area shape reference")
        references = {}
        for identity in sorted(ids):
            if identity not in features or features[identity]["properties"]["shape_id"] != identity:
                raise ValueError("Missing or mismatched shape reference")
            raw = encoded(
                {
                    "schema_version": "tram-shape-object-v1",
                    "chunk_policy": POLICY,
                    "source_revision": source["source_archive_sha256"],
                    "feature": features[identity],
                }
            )
            checksum = digest(raw)
            path = f"objects/{checksum}.json"
            files[path] = raw
            reference = {"path": path, "sha256": checksum, "bytes": len(raw)}
            references[identity] = reference
            objects[identity] = reference
        manifest = encoded(
            {
                "schema_version": "tram-area-shapes-v1",
                "chunk_policy": POLICY,
                "area_id": area_id,
                "name": area["name"],
                "boundary_sha256": area["boundary_sha256"],
                "source": source,
                "shapes": references,
            }
        )
        checksum = digest(manifest)
        path = f"areas/{checksum}.json"
        files[path] = manifest
        object_bytes = sum(r["bytes"] for r in references.values())
        area_records[area_id] = {
            "manifest": {"path": path, "sha256": checksum, "bytes": len(manifest)},
            "shape_count": len(references),
            "object_bytes": object_bytes,
            "cold_bytes": len(manifest) + object_bytes,
            "cold_requests": 1 + len(references),
        }
    return files, {
        "chunk_policy": POLICY,
        "source_revision": source["source_archive_sha256"],
        "areas": area_records,
        "unique_objects": len(objects),
        "object_bytes": sum(r["bytes"] for r in objects.values()),
        "limits": "Offline build only. Byte counts exclude HTTP headers, compression and "
        "browser memory. No loader, serving URL or deployment is enabled.",
    }


def publish(path: Path, raw: bytes) -> None:
    """Publish complete immutable bytes, or verify an existing object on a repeat build."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("Existing content-addressed file differs")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pool-", delete=False) as temp:
        temporary = Path(temp.name)
        try:
            temp.write(raw)
            temp.flush()
            os.fsync(temp.fileno())
        except BaseException:
            temp.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise ValueError("Existing content-addressed file differs") from None
    finally:
        temporary.unlink(missing_ok=True)


def write_pool(output: Path, files: dict[str, bytes], report: dict) -> str:
    # Objects are published before manifests, and the report/discovery pointer last.
    for name in sorted(files, key=lambda name: (not name.startswith("objects/"), name)):
        publish(output / name, files[name])
    raw = encoded(report)
    name = f"reports/{digest(raw)}.json"
    publish(output / name, raw)
    return name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    files, report = build_pool(index, load_inputs(index, ROOT))
    name = write_pool(args.output, files, report)
    print(
        json.dumps({"report": name, "objects": report["unique_objects"], "areas": report["areas"]})
    )


if __name__ == "__main__":
    main()
