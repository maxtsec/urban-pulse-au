"""Bounded memoization of fixture geometry/point checks against real PostGIS."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, cast

import psycopg
from sqlalchemy.engine import Engine


class PostgisMembership:
    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self.database_url = database_url
        self.engine = engine
        self._cached_overlap = lru_cache(maxsize=64)(self._query_overlap)
        self._cached_covers = lru_cache(maxsize=32)(self._query_covers)

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        if self.engine is None:
            with psycopg.connect(self.database_url, connect_timeout=3) as connection:
                yield connection
        else:
            # The engine owns checkout and transaction cleanup; never close its raw driver.
            with self.engine.begin() as pooled:
                yield cast(psycopg.Connection[Any], pooled.connection.driver_connection)

    def covers(self, geometry: dict[str, Any], points: list[tuple[float, float]]) -> list[bool]:
        encoded = json.dumps(geometry, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return list(self._cached_covers(encoded, tuple(points)))

    def _query_covers(
        self, encoded: str, points: tuple[tuple[float, float], ...]
    ) -> tuple[bool, ...]:
        # Only geometry/point results are cached, never time-dependent conditions or DB failures.
        with self._connection() as connection:
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

    def overlaps(self, area: dict[str, Any], warning: dict[str, Any]) -> bool | None:
        encoded = tuple(
            json.dumps(geom, sort_keys=True, separators=(",", ":"), allow_nan=False)
            for geom in (area, warning)
        )
        return self._cached_overlap(*encoded)

    def _query_overlap(self, area: str, warning: str) -> bool | None:
        with self._connection() as connection:
            connection.execute("SET LOCAL statement_timeout = '3000ms'")
            row = connection.execute(
                """WITH shapes AS MATERIALIZED (
                    SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) AS area,
                           ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) AS warning
                ), checked AS MATERIALIZED (
                    SELECT *, ST_IsValid(area) AND ST_IsValid(warning)
                      AND NOT ST_IsEmpty(area) AND NOT ST_IsEmpty(warning)
                      AND GeometryType(area) IN ('POLYGON','MULTIPOLYGON')
                      AND GeometryType(warning) IN ('POLYGON','MULTIPOLYGON')
                      AND ST_XMin(Box3D(warning)) >= -180 AND ST_XMax(Box3D(warning)) <= 180
                      AND ST_YMin(Box3D(warning)) >= -90 AND ST_YMax(Box3D(warning)) <= 90 AS valid
                    FROM shapes
                ) SELECT CASE WHEN valid THEN
                    ST_Relate(area, warning, '2********') ELSE NULL END FROM checked""",
                (area, warning),
            ).fetchone()
        return None if row is None or row[0] is None else bool(row[0])
