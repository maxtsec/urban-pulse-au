FROM ghcr.io/astral-sh/uv:0.12.23 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-default-groups
COPY apps ./apps
COPY workers ./workers
COPY tests/fixtures ./tests/fixtures
CMD ["uv", "run", "--no-sync", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
