"""Real boundary selection remains independent of the shared route-asset partition."""

import json

import psycopg
import pytest

from scripts.build_tram_area_fixture import OUTPUT, ROOT
from scripts.build_tram_fixture import select_full_shapes
from urbanpulse.config import Settings

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("area", ["southbank", "melbourne-cbd"])
def test_each_area_reselects_its_exact_routes_from_shared_assets(area):
    index = json.loads((OUTPUT / "index.json").read_text(encoding="utf-8"))
    features = []
    for path in index["assets"]:
        features.extend(json.loads((ROOT / path).read_text(encoding="utf-8"))["features"])
    by_id = {f["properties"]["shape_id"]: f for f in features}
    record = index["areas"][area]
    boundary = json.loads((ROOT / record["boundary_path"]).read_text(encoding="utf-8"))
    shapes = [{"id": i, "geometry": f["geometry"]} for i, f in by_id.items()]
    with psycopg.connect(Settings().database_url, connect_timeout=3) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL statement_timeout = '120s'")
        selected = select_full_shapes(connection, shapes, boundary["geometry"])
    assert [f["properties"]["shape_id"] for f in selected["features"]] == record["shape_ids"]
    for feature in selected["features"]:
        retained = by_id[feature["properties"]["shape_id"]]
        assert feature["geometry"] == retained["geometry"]
        assert feature["properties"]["distances_m"] == retained["properties"]["distances_m"]
