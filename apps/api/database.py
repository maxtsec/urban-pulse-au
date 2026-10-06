"""One bounded database resource owner per API process/lifespan."""

from urbanpulse.adapters.city_store import CityInputStore, engine_for
from urbanpulse.adapters.postgis import PostgisMembership


class ApiDatabase:
    def __init__(self, url: str) -> None:
        self.engine = engine_for(url, pool_size=2, max_overflow=0, pool_timeout=1)
        self.inputs = CityInputStore(self.engine)
        self.spatial = PostgisMembership(url, engine=self.engine)

    def probe(self) -> None:
        with self.engine.begin() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout = '3000ms'")
            connection.exec_driver_sql("SELECT PostGIS_Version()").fetchone()

    def close(self) -> None:
        self.engine.dispose()
