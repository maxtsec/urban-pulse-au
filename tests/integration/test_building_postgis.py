"""Validate retained and rounded building footprints against the real Southbank polygon."""

import json
import os

import psycopg
import pytest

from scripts.build_building_fixture import BOUNDARY, FIXTURE

pytestmark = pytest.mark.integration


def test_every_retained_structure_is_valid_and_intersects_southbank():
    boundary = json.loads(BOUNDARY.read_text())["geometry"]
    collection = json.loads(FIXTURE.read_text())
    with psycopg.connect(
        os.environ.get(
            "URBANPULSE_TEST_DATABASE_URL",
            "postgresql://urbanpulse:urbanpulse_local@127.0.0.1:5432/urbanpulse",
        )
    ) as connection:
        row = connection.execute(
            """
            WITH footprints AS (
                SELECT ST_SetSRID(ST_GeomFromGeoJSON(feature->>'geometry'),4326) AS g
                FROM jsonb_array_elements(%s::jsonb->'features') AS feature
            )
            SELECT count(*), bool_and(ST_IsValid(g)),
                   bool_and(ST_Intersects(g, ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)))
            FROM footprints
        """,
            (json.dumps(collection), json.dumps(boundary)),
        ).fetchone()
    assert row == (1108, True, True)
