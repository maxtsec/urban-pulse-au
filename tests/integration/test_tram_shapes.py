"""Actual PostGIS clipping: source order, gaps, holes and edge contact."""

import json

import psycopg
import pytest

from scripts.build_tram_fixture import BOUNDARY, OUTPUT, clip_shapes
from urbanpulse.config import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def connection():
    with psycopg.connect(Settings().database_url, connect_timeout=3) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn


def polygon(ring, holes=()):
    return {"type": "Polygon", "coordinates": [ring, *holes]}


def test_clip_keeps_offset_direction_and_excluded_hole_separate(connection):
    boundary = polygon(
        [[144.95, -37.83], [144.97, -37.83], [144.97, -37.81], [144.95, -37.81], [144.95, -37.83]],
        [
            [
                [144.957, -37.825],
                [144.963, -37.825],
                [144.963, -37.815],
                [144.957, -37.815],
                [144.957, -37.825],
            ]
        ],
    )
    shapes = [
        {
            "id": "forward",
            "geometry": {"type": "LineString", "coordinates": [[144.94, -37.82], [144.98, -37.82]]},
        },
        {
            "id": "reverse",
            "geometry": {"type": "LineString", "coordinates": [[144.98, -37.82], [144.94, -37.82]]},
        },
    ]
    geo = clip_shapes(connection, shapes, boundary)
    assert len(geo["features"]) == 4
    for identity in ("forward", "reverse"):
        parts = [f for f in geo["features"] if f["properties"]["shape_id"] == identity]
        first, last = parts
        assert first["properties"]["distances_m"][0] > 800
        assert last["properties"]["distances_m"][0] > first["properties"]["distances_m"][-1] + 400
        for part in parts:
            xs = [p[0] for p in part["geometry"]["coordinates"]]
            assert (xs[0] < xs[-1]) == (identity == "forward")


def test_point_contact_does_not_become_a_route_segment(connection):
    boundary = polygon(
        [[144.95, -37.83], [144.97, -37.83], [144.97, -37.81], [144.95, -37.81], [144.95, -37.83]]
    )
    shape = {
        "id": "touch",
        "geometry": {"type": "LineString", "coordinates": [[144.94, -37.84], [144.95, -37.83]]},
    }
    assert clip_shapes(connection, [shape], boundary)["features"] == []


def test_committed_geometry_is_inside_boundary_to_numeric_precision(connection):
    boundary = json.loads(BOUNDARY.read_text(encoding="utf-8"))["geometry"]
    shapes = json.loads((OUTPUT / "southbank-tram-shapes.geojson").read_text(encoding="utf-8"))
    # 2 cm is a round-trip numeric allowance, not a live matching tolerance or area buffer.
    result = connection.execute(
        """WITH b AS (
      SELECT ST_Buffer(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32755),0.02) geom
    ) SELECT bool_and(ST_Covers(b.geom,
        ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(f->'geometry'),4326),32755)))
      FROM b CROSS JOIN jsonb_array_elements(%s::jsonb->'features') f""",
        (json.dumps(boundary), json.dumps(shapes)),
    ).fetchone()
    assert result[0] is True
