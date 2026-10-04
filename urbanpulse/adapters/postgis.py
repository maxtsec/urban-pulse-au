"""Bounded memoization of fixture geometry/point checks against real PostGIS."""

import json
from functools import lru_cache
from typing import Any

import psycopg


class PostgisMembership:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._cached_covers = lru_cache(maxsize=32)(self._query_covers)

    def covers(self, geometry: dict[str, Any], points: list[tuple[float, float]]) -> list[bool]:
        encoded = json.dumps(geometry, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return list(self._cached_covers(encoded, tuple(points)))

    def _query_covers(
        self, encoded: str, points: tuple[tuple[float, float], ...]
    ) -> tuple[bool, ...]:
        # Only geometry/point results are cached, never time-dependent conditions or DB failures.
        with psycopg.connect(self.database_url, connect_timeout=3) as connection:
            connection.execute("SET LOCAL statement_timeout = '3000ms'")
            row = connection.execute(
                """WITH boundary AS MATERIALIZED (
                    SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) AS geom
                ), checked AS MATERIALIZED (
                    SELECT geom, ST_IsValid(geom) AND NOT ST_IsEmpty(geom)
                      AND GeometryType(geom) IN ('POLYGON', 'MULTIPOLYGON')
                      AND ST_XMin(Box3D(geom)) >= -180 AND ST_XMax(Box3D(geom)) <= 180
                      AND ST_YMin(Box3D(geom)) >= -90 AND ST_YMax(Box3D(geom)) <= 90 AS valid
                    FROM boundary
                )
                SELECT valid, CASE WHEN valid THEN ARRAY(
                    SELECT ST_Covers(geom, ST_SetSRID(ST_MakePoint(
                        (p.value->>0)::double precision, (p.value->>1)::double precision
                    ), 4326))
                    FROM jsonb_array_elements(%s::jsonb) WITH ORDINALITY AS p(value, n)
                    ORDER BY p.n
                ) ELSE ARRAY[]::boolean[] END FROM checked""",
                (encoded, json.dumps(points, allow_nan=False)),
            ).fetchone()
        if row is None or row[0] is not True:
            raise ValueError("invalid area boundary")
        return tuple(bool(value) for value in row[1])
