"""Offline smoke asset. Cloud loading and publication are future implementation."""

import polars as pl
from dagster import AssetExecutionContext, Definitions, asset

from urbanpulse.config import ROOT


@asset
def fixture_parquet(context: AssetExecutionContext) -> None:
    import json

    payload = json.loads((ROOT / "tests/fixtures/transport.json").read_text())
    frame = pl.DataFrame(payload["observations"])
    destination = ROOT / ".local/curated/fixture.parquet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(destination)
    context.add_output_metadata({"rows": frame.height, "mode": "fixture"})


defs = Definitions(assets=[fixture_parquet])
