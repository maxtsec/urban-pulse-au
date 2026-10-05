"""Version observation event slots without changing envelopes or import identities.

The conversion is frozen here so later runtime codecs cannot change this migration.
"""

import hashlib
import json

import sqlalchemy as sa
from alembic import op

revision = "0003_observation_codec"
down_revision = "0002_active_import"
branch_labels = None
depends_on = None
OWNERS = ("transport", "weather", "planning")


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def legacy_descriptor(value):
    if not isinstance(value, dict):
        raise ValueError("invalid legacy observation event slot")
    if set(value) == {"rejected_event"} and isinstance(value["rejected_event"], str):
        return {"kind": "rejected", "envelope": value["rejected_event"]}
    if set(value) not in ({"event_reference"}, {"event_reference", "attempt_envelope"}):
        raise ValueError("ambiguous legacy observation event descriptor")
    key = value["event_reference"]
    if not isinstance(key, list) or len(key) != 2 or not all(isinstance(x, str) for x in key):
        raise ValueError("invalid legacy event reference")
    result = {"kind": "reference", "source": key[0], "id": key[1]}
    if "attempt_envelope" in value:
        if not isinstance(value["attempt_envelope"], str):
            raise ValueError("invalid legacy attempt envelope")
        result["attempt_envelope"] = value["attempt_envelope"]
    return result


def current_descriptor(value):
    if not isinstance(value, dict):
        raise ValueError("invalid observation event descriptor")
    if value.get("kind") == "rejected":
        if set(value) != {"kind", "envelope"} or not isinstance(value["envelope"], str):
            raise ValueError("invalid rejected observation")
    elif value.get("kind") == "reference":
        required = {"kind", "source", "id"}
        if not required <= value.keys() or value.keys() - required - {"attempt_envelope"}:
            raise ValueError("invalid observation reference fields")
        if not all(isinstance(value[k], str) for k in ("source", "id")):
            raise ValueError("invalid observation reference identity")
        if "attempt_envelope" in value and not isinstance(value["attempt_envelope"], str):
            raise ValueError("invalid observation attempt envelope")
    else:
        raise ValueError("unknown observation descriptor")
    return value


def opaque_is_legacy_safe(value):
    if isinstance(value, dict):
        return (
            "event_reference" not in value
            and set(value) != {"rejected_event"}
            and all(opaque_is_legacy_safe(item) for item in value.values())
        )
    if isinstance(value, list):
        return all(opaque_is_legacy_safe(item) for item in value)
    return True


def rewrite(upgrading):
    connection = op.get_bind()
    for imported in connection.execute(sa.text("SELECT * FROM city04_imports")).mappings():
        scope = imported["id"]
        if imported["normalizer_version"] != "city-normalizer-v2":
            # Pre-existing unsupported exports keep their bytes and legacy version.
            if not upgrading:
                for owner in OWNERS:
                    versions = connection.execute(
                        sa.text(
                            f"SELECT DISTINCT codec_version FROM city04_{owner}_observations "
                            "WHERE scope=:scope"
                        ),
                        {"scope": scope},
                    ).scalars()
                    if any(version != 1 for version in versions):
                        raise ValueError("cannot downgrade an unknown normalizer's current codec")
            continue
        decoded = {}
        updates = []
        for owner in OWNERS:
            table = f"city04_{owner}_observations"
            known = {
                (row["source"], row["event_id"]): json.loads(row["envelope"])
                for row in connection.execute(
                    sa.text(f"SELECT * FROM city04_{owner}_revisions WHERE scope = :scope"),
                    {"scope": scope},
                ).mappings()
            }
            decoded[owner] = []
            for record in connection.execute(
                sa.text(f"SELECT * FROM {table} WHERE scope = :scope ORDER BY sequence"),
                {"scope": scope},
            ).mappings():
                if record["codec_version"] != (1 if upgrading else 2):
                    raise ValueError("unexpected observation codec during migration")
                row = json.loads(record["body"])
                slots = ("events", "warning_records") if owner == "weather" else ("event",)
                if not isinstance(row, dict) or not all(slot in row for slot in slots):
                    raise ValueError("missing declared observation event slot")
                opaque = {key: value for key, value in row.items() if key not in slots}
                if not upgrading and not opaque_is_legacy_safe(opaque):
                    raise ValueError("unsafe codec downgrade: literal event tags require version 2")
                body, decoded_row = dict(opaque), dict(opaque)
                for slot in slots:
                    values = row[slot] if slot != "event" else [row[slot]]
                    if not isinstance(values, list):
                        raise ValueError("invalid observation event list")
                    converted, envelopes = [], []
                    for value in values:
                        if value is None and slot == "event":
                            converted.append(None)
                            envelopes.append(None)
                            continue
                        descriptor = (
                            legacy_descriptor(value) if upgrading else current_descriptor(value)
                        )
                        if descriptor["kind"] == "rejected":
                            envelope = json.loads(descriptor["envelope"])
                            legacy = {"rejected_event": descriptor["envelope"]}
                        else:
                            key = (descriptor["source"], descriptor["id"])
                            if key not in known:
                                raise ValueError("observation references a missing revision")
                            envelope = known[key]
                            legacy = {"event_reference": list(key)}
                            if "attempt_envelope" in descriptor:
                                envelope = json.loads(descriptor["attempt_envelope"])
                                legacy["attempt_envelope"] = descriptor["attempt_envelope"]
                            if (envelope.get("source"), envelope.get("id")) != key:
                                raise ValueError("observation envelope identity mismatch")
                        converted.append(descriptor if upgrading else legacy)
                        envelopes.append(envelope)
                    decoded_row[slot] = envelopes if slot != "event" else envelopes[0]
                    body[slot] = converted if slot != "event" else converted[0]
                decoded[owner].append(decoded_row)
                updates.append((table, record["sequence"], encode(body)))
        digest = hashlib.sha256(
            encode([json.loads(imported["metadata_json"]), decoded]).encode()
        ).hexdigest()
        if digest != imported["content_hash"]:
            raise ValueError(f"observation migration integrity mismatch for import {scope}")
        for table, sequence, body in updates:
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET body=:body, codec_version=:version "
                    "WHERE scope=:scope AND sequence=:sequence"
                ),
                {
                    "body": body,
                    "version": 2 if upgrading else 1,
                    "scope": scope,
                    "sequence": sequence,
                },
            )


def upgrade():
    for owner in OWNERS:
        op.add_column(
            f"city04_{owner}_observations",
            sa.Column("codec_version", sa.Integer(), nullable=False, server_default="1"),
        )
    rewrite(upgrading=True)
    for owner in OWNERS:
        op.alter_column(f"city04_{owner}_observations", "codec_version", server_default="2")


def downgrade():
    rewrite(upgrading=False)
    for owner in OWNERS:
        op.drop_column(f"city04_{owner}_observations", "codec_version")
