"""PostGIS selects complete routes without splitting boundary crossings or holes."""

import json

import psycopg
import pytest

from scripts.build_tram_fixture import BOUNDARY, OUTPUT, area_vertices, select_full_shapes
from urbanpulse.config import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def connection():
    with psycopg.connect(Settings().database_url, connect_timeout=3) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn


def polygon(ring, holes=()):
    return {"type": "Polygon", "coordinates": [ring, *holes]}


def test_full_shapes_keep_direction_and_path_through_excluded_hole(connection):
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
    geo = select_full_shapes(connection, shapes, boundary)
    assert len(geo["features"]) == 2
    for source, feature in zip(shapes, geo["features"], strict=True):
        assert feature["geometry"] == source["geometry"]
        assert feature["properties"]["segment_id"] == source["id"] + "/full"
        distances = feature["properties"]["distances_m"]
        assert distances[0] == 0 and distances[-1] > 3000


def test_point_contact_does_not_become_a_route_segment(connection):
    boundary = polygon(
        [[144.95, -37.83], [144.97, -37.83], [144.97, -37.81], [144.95, -37.81], [144.95, -37.83]]
    )
    shape = {
        "id": "touch",
        "geometry": {"type": "LineString", "coordinates": [[144.94, -37.84], [144.95, -37.83]]},
    }
    outside = {
        "id": "outside",
        "geometry": {"type": "LineString", "coordinates": [[144.90, -37.82], [144.91, -37.82]]},
    }
    assert select_full_shapes(connection, [shape, outside], boundary)["features"] == []


def test_committed_shapes_intersect_pilot_but_retain_outside_geometry(connection):
    boundary = json.loads(BOUNDARY.read_text(encoding="utf-8"))["geometry"]
    shapes = json.loads((OUTPUT / "southbank-tram-shapes.geojson").read_text(encoding="utf-8"))
    result = connection.execute(
        """WITH b AS (
          SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32755) geom
        ), shapes AS (
          SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(f->'geometry'),4326),32755) geom
          FROM jsonb_array_elements(%s::jsonb->'features') f
        ) SELECT bool_and(ST_Length(ST_CollectionExtract(ST_Intersection(b.geom,s.geom),2))
          > 0.000001), bool_or(NOT ST_Covers(b.geom,s.geom)) FROM b CROSS JOIN shapes s""",
        (json.dumps(boundary), json.dumps(shapes)),
    ).fetchone()
    assert result == (True, True)
    data = json.loads((OUTPUT / "trip-observations.json").read_text(encoding="utf-8"))
    in_area = area_vertices(connection, shapes, boundary)
    by_shape = {f["properties"]["shape_id"]: f for f in shapes["features"]}
    links = {t["trip_id"]: t for t in data["static_trip_links"]}
    for frame in data["frames"]:
        state = frame["event"]["data"]["state"]
        identity = links[state["trip"]["trip_id"]]["shape_id"]
        point = [state["position"]["longitude"], state["position"]["latitude"]]
        assert point in [
            by_shape[identity]["geometry"]["coordinates"][i] for i in in_area[identity]
        ]


def test_positive_length_boundary_overlap_keeps_complete_shape(connection):
    boundary = polygon(
        [[144.95, -37.83], [144.97, -37.83], [144.97, -37.81], [144.95, -37.81], [144.95, -37.83]]
    )
    source = {
        "id": "edge",
        "geometry": {"type": "LineString", "coordinates": boundary["coordinates"][0][:2]},
    }
    result = select_full_shapes(connection, [source], boundary)
    assert len(result["features"]) == 1
    assert result["features"][0]["geometry"] == source["geometry"]


def test_reentry_and_coincident_vertices_do_not_split_or_reorder_shape(connection):
    boundary = polygon(
        [[144.95, -37.83], [144.97, -37.83], [144.97, -37.81], [144.95, -37.81], [144.95, -37.83]]
    )
    coords = [
        [144.96, -37.82],
        [144.96, -37.82],
        [144.98, -37.82],
        [144.98, -37.815],
        [144.96, -37.815],
    ]
    source = {"id": "s", "geometry": {"type": "LineString", "coordinates": coords}}
    result = select_full_shapes(connection, [source], boundary)
    assert len(result["features"]) == 1
    feature = result["features"][0]
    assert feature["geometry"]["coordinates"] == coords
    distances = feature["properties"]["distances_m"]
    assert distances[:2] == [0, 0]
    assert all(b > a for a, b in zip(distances[1:], distances[2:], strict=False))
    assert area_vertices(connection, result, boundary) == {"s": [0, 1, 4]}
