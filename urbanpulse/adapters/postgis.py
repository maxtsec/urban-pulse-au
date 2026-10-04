"""PostGIS boundary validation and batched point coverage without persistent fixture tables."""

import json
from typing import Any

import psycopg


class PostgisMembership:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def covers(self, geometry: dict[str, Any], points: list[tuple[float, float]]) -> list[bool]:
        encoded = json.dumps(geometry, allow_nan=False)
        with psycopg.connect(self.database_url, connect_timeout=3) as connection:
            connection.execute("SET LOCAL statement_timeout = '3000ms'")
            valid = connection.execute(
                """WITH boundary AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS geom)
                SELECT ST_IsValid(geom) AND NOT ST_IsEmpty(geom)
                  AND GeometryType(geom) IN ('POLYGON', 'MULTIPOLYGON')
                  AND ST_XMin(Box3D(geom)) >= -180 AND ST_XMax(Box3D(geom)) <= 180
                  AND ST_YMin(Box3D(geom)) >= -90 AND ST_YMax(Box3D(geom)) <= 90
                FROM boundary""",
                (encoded,),
            ).fetchone()
            if valid is None or valid[0] is not True:
                raise ValueError("invalid area boundary")
            rows = connection.execute(
                """WITH boundary AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS geom)
                SELECT ST_Covers(geom, ST_SetSRID(ST_MakePoint(
                    (p.value->>0)::double precision, (p.value->>1)::double precision
                ), 4326))
                FROM boundary, jsonb_array_elements(%s::jsonb) WITH ORDINALITY AS p(value, n)
                ORDER BY p.n""",
                (encoded, json.dumps(points, allow_nan=False)),
            ).fetchall()
        return [bool(row[0]) for row in rows]
