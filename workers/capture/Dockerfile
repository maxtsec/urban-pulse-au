FROM ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 AS uv
FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS runtime
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-default-groups
COPY urbanpulse ./urbanpulse
COPY workers/__init__.py ./workers/__init__.py
COPY workers/capture ./workers/capture
RUN useradd --uid 10001 --no-create-home collector
ARG COLLECTOR_VERSION=local-unversioned
USER 10001:10001
ENV COLLECTOR_VERSION=$COLLECTOR_VERSION
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
ENTRYPOINT ["/app/.venv/bin/python", "-m", "workers.capture.main"]
CMD ["--help"]

FROM runtime AS test
USER root
RUN uv sync --locked --no-default-groups --group dev
COPY tests/test_transport_capture.py tests/test_capture_journal.py tests/test_local_collector.py ./tests/
COPY tests/helpers/capture_process.py ./tests/helpers/capture_process.py
USER 10001:10001
ENTRYPOINT ["/app/.venv/bin/python", "-m", "pytest"]
CMD ["-q", "-p", "no:cacheprovider", "tests/test_transport_capture.py", "tests/test_capture_journal.py", "tests/test_local_collector.py"]
