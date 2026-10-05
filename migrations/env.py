"""Run reviewed application migrations using private runtime configuration."""

from alembic import context

from urbanpulse.adapters.city_store import engine_for
from urbanpulse.config import Settings

url = context.config.attributes.get("database_url") or Settings().database_url
engine = engine_for(url)
try:
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
