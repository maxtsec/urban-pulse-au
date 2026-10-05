"""Upgrade real v1 history in isolated PostgreSQL schemas, including failed migrations."""

import json
import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from urbanpulse.adapters.city_fixture import LocalCityCapture, capture_city
from urbanpulse.adapters.city_import import prepare_import
from urbanpulse.adapters.city_store import CityInputStore, DomainExport, encode, engine_for
from urbanpulse.adapters.planning_fixture import FixturePlanningNormalizer
from urbanpulse.adapters.postgis import PostgisMembership
from urbanpulse.adapters.weather_fixture import FixtureWeatherNormalizer
from urbanpulse.application.capture_replay import payload_hash
from urbanpulse.application.city import CityService
from urbanpulse.config import ROOT
from urbanpulse.contracts.events import CloudEvent, EventReceipt

pytestmark = pytest.mark.integration
URL = os.environ.get(
    "URBANPULSE_TEST_DATABASE_URL",
    "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse",
)


def migrate_to(url, target, *, downgrade=False):
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = url
    (command.downgrade if downgrade else command.upgrade)(config, target)


@pytest.fixture
def database(tmp_path):
    schema = "codec_test_" + uuid4().hex
    admin = engine_for(URL)
    with admin.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(URL).update_query_dict({"options": f"-csearch_path={schema}"})
    private_url = url.render_as_string(hide_password=False)
    engine = engine_for(private_url)
    try:
        migrate_to(private_url, "0002_active_import")
        captured = LocalCityCapture(tmp_path, capture_city(tmp_path)).read()
        spatial = PostgisMembership(URL)
        rows = prepare_import(captured, spatial)
        yield private_url, engine, captured, rows, spatial
    finally:
        engine.dispose()
        # This generated schema belongs only to this test, never the development schema.
        with admin.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def seed_legacy(engine, captured, rows):
    """Frozen v1 row writer, independent of the new codec and its downgrade path."""
    scope = payload_hash([captured.capture_id, "city-normalizer-v2"])
    info = {
        "boundary": captured.boundary,
        "scenario": {
            k: v for k, v in captured.scenario.items() if k not in {"frames", "service_frames"}
        },
        "weather": {"outage_at_seconds": captured.weather["outage_at_seconds"]},
        "planning": {"outage_at_seconds": captured.planning["outage_at_seconds"]},
    }

    def raw(value):
        if isinstance(value, CloudEvent):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {k: raw(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [raw(v) for v in value]
        return value

    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO city04_imports VALUES (:id,:capture,:normalizer,:metadata,:hash)"),
            {
                "id": scope,
                "capture": captured.capture_id,
                "normalizer": "city-normalizer-v2",
                "metadata": encode(info),
                "hash": payload_hash(json.loads(encode([info, raw(rows)]))),
            },
        )
        connection.execute(
            sa.text("INSERT INTO city04_active_imports VALUES ('city-fixture',:scope)"),
            {"scope": scope},
        )
        for owner in ("transport", "weather", "planning"):
            known, aggregates = {}, set()

            def reference(value, known=known, aggregates=aggregates, owner=owner):
                if isinstance(value, CloudEvent):
                    key = (value.source, value.id)
                    aggregate = (value.source, value.subject, value.data.revision)
                    receipt = EventReceipt.from_event(value)
                    wire = value.model_dump_json()
                    if (
                        key in known
                        and known[key][0] != receipt
                        or key not in known
                        and aggregate in aggregates
                    ):
                        return {"rejected_event": wire}
                    if key not in known:
                        known[key] = receipt, wire
                        aggregates.add(aggregate)
                        connection.execute(
                            sa.text(
                                f"INSERT INTO city04_{owner}_revisions VALUES "
                                "(:scope,:source,:id,:subject,:revision,:fingerprint,:envelope)"
                            ),
                            {
                                "scope": scope,
                                "source": value.source,
                                "id": value.id,
                                "subject": value.subject,
                                "revision": value.data.revision,
                                "fingerprint": receipt.fingerprint,
                                "envelope": wire,
                            },
                        )
                    result = {"event_reference": list(key)}
                    if known[key][1] != wire:
                        result["attempt_envelope"] = wire
                    return result
                if isinstance(value, dict):
                    return {k: reference(v) for k, v in value.items()}
                if isinstance(value, (tuple, list)):
                    return [reference(v) for v in value]
                return value

            for sequence, row in enumerate(rows[owner]):
                connection.execute(
                    sa.text(
                        f"INSERT INTO city04_{owner}_observations "
                        "VALUES (:scope,:seq,:seconds,:body)"
                    ),
                    {
                        "scope": scope,
                        "seq": sequence,
                        "seconds": row["frame"]["at_seconds"],
                        "body": encode(reference(row)),
                    },
                )
    return scope


def saved_rows(engine):
    result = {}
    names = ["alembic_version", "city04_imports", "city04_active_imports"]
    names += [
        f"city04_{owner}_{kind}"
        for owner in ("transport", "weather", "planning")
        for kind in ("revisions", "observations")
    ]
    with engine.connect() as connection:
        for name in names:
            result[name] = sorted(
                encode(dict(row))
                for row in connection.execute(sa.text(f"SELECT * FROM {name}")).mappings()
            )
    return result


def test_legacy_upgrade_preserves_history_envelopes_trace_context_and_selection(database):
    url, engine, captured, rows, spatial = database
    scope = seed_legacy(engine, captured, rows)
    before = saved_rows(engine)
    migrate_to(url, "head")
    after = saved_rows(engine)
    for table, values in before.items():
        if table.endswith("_revisions") or table in {"city04_imports", "city04_active_imports"}:
            assert after[table] == values
    store = CityInputStore(engine)
    assert store.active_scope() == scope
    with engine.connect() as connection:
        for owner in rows:
            assert encode(DomainExport(owner).read(connection, scope)) == encode(rows[owner])
    assert store.save(captured, rows) == scope
    inputs = store.load(scope)
    recovered = CityService(inputs, spatial, inputs=inputs)
    original = CityService(
        type("Capture", (), {"read": lambda self: captured})(),
        spatial,
        FixtureWeatherNormalizer(),
        FixturePlanningNormalizer(),
    )
    for seconds in (0, 60, 150, 180, 240, 270, 360):
        assert encode(recovered.snapshot(seconds, "city")) == encode(
            original.snapshot(seconds, "city")
        )
    migrate_to(url, "0002_active_import", downgrade=True)
    assert saved_rows(engine) == before
    migrate_to(url, "head")
    assert store.load(scope).captured.capture_id == captured.capture_id


def test_literal_reference_fields_survive_upgrade_and_make_unsafe_downgrade_fail(database):
    url, engine, captured, rows, spatial = database
    literal = {
        "event_reference": ["ordinary", "data"],
        "nested": [{"rejected_event": "not an envelope"}],
    }
    rows["weather"][0]["evidence"]["extra"] = literal
    scope = seed_legacy(engine, captured, rows)
    migrate_to(url, "head")
    inputs = CityInputStore(engine).load(scope)
    assert inputs.weather[0].evidence["extra"] == literal
    before = saved_rows(engine)
    with pytest.raises(ValueError, match="unsafe codec downgrade"):
        migrate_to(url, "0002_active_import", downgrade=True)
    assert saved_rows(engine) == before


@pytest.mark.parametrize("corruption", ["ambiguous", "missing", "hash", "null"])
def test_bad_legacy_import_rolls_back_schema_and_all_data(database, corruption):
    url, engine, captured, rows, spatial = database
    seed_legacy(engine, captured, rows)
    with engine.begin() as connection:
        body = json.loads(
            connection.execute(
                sa.text("SELECT body FROM city04_transport_observations WHERE sequence=0")
            ).scalar_one()
        )
        if corruption == "ambiguous":
            body["event"]["unexpected"] = True
        elif corruption == "missing":
            body["event"]["event_reference"][1] = "missing"
        elif corruption == "null":
            body["event"] = []
        else:
            body["frame"]["at_seconds"] = 999
        connection.execute(
            sa.text("UPDATE city04_transport_observations SET body=:body WHERE sequence=0"),
            {"body": encode(body)},
        )
    before = saved_rows(engine)
    with pytest.raises(ValueError):
        migrate_to(url, "head")
    assert saved_rows(engine) == before
    with engine.connect() as connection:
        assert (
            "codec_version"
            not in connection.execute(
                sa.text("SELECT * FROM city04_transport_observations LIMIT 1")
            ).keys()
        )


def test_unsupported_older_normalizer_remains_untouched_and_unavailable(database):
    url, engine, captured, rows, spatial = database
    scope = seed_legacy(engine, captured, rows)
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE city04_imports SET normalizer_version='city-normalizer-v1'")
        )
    before = saved_rows(engine)
    migrate_to(url, "head")
    after = saved_rows(engine)
    for table, values in before.items():
        if table == "alembic_version":
            continue
        if table.endswith("_observations"):
            actual = [json.loads(value) for value in after[table]]
            assert all(row.pop("codec_version") == 1 for row in actual)
            assert sorted(encode(row) for row in actual) == values
        else:
            assert after[table] == values
    with pytest.raises(ValueError, match="inputs missing"):
        CityInputStore(engine).load(scope)
    with pytest.raises(ValueError, match="not selected"):
        CityInputStore(engine).active_scope()
    migrate_to(url, "0002_active_import", downgrade=True)
    assert saved_rows(engine) == before
