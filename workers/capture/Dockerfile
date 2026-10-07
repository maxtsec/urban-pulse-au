FROM ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 AS uv
FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --only-group capture --no-default-groups

FROM dependencies AS test-dependencies
RUN uv sync --locked --only-group capture-test --no-default-groups

FROM python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS runtime
WORKDIR /app
COPY --from=dependencies /app/.venv /app/.venv
COPY urbanpulse/__init__.py ./urbanpulse/__init__.py
COPY urbanpulse/contracts/__init__.py urbanpulse/contracts/local_capture.py urbanpulse/contracts/capture_control.py urbanpulse/contracts/capture_delivery.py ./urbanpulse/contracts/
COPY urbanpulse/adapters/__init__.py urbanpulse/adapters/capture_journal.py urbanpulse/adapters/capture_checkpoint.py urbanpulse/adapters/capture_verify.py urbanpulse/adapters/capture_v3.py urbanpulse/adapters/capture_v3_verify.py urbanpulse/adapters/synthetic_capture.py urbanpulse/adapters/transport_capture.py ./urbanpulse/adapters/
COPY urbanpulse/application/__init__.py urbanpulse/application/local_collector.py urbanpulse/application/tram_schedule.py ./urbanpulse/application/
COPY workers/__init__.py ./workers/__init__.py
COPY workers/capture/*.py ./workers/capture/
RUN useradd --uid 10001 --no-create-home collector
ARG COLLECTOR_VERSION=local-unversioned
USER 10001:10001
ENV COLLECTOR_VERSION=$COLLECTOR_VERSION
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
ENTRYPOINT ["/app/.venv/bin/python", "-m", "workers.capture.main"]
CMD ["--help"]

FROM runtime AS test
COPY --from=test-dependencies /app/.venv /app/.venv
COPY pyproject.toml ./
COPY tests/test_transport_capture.py tests/test_capture_journal.py tests/test_local_collector.py tests/test_capture_checkpoint.py tests/test_capture_v3.py ./tests/
COPY tests/helpers/capture_process.py tests/helpers/checkpoint_process.py tests/helpers/benchmark_capture.py tests/helpers/delivery_process.py tests/helpers/v3_records.py ./tests/helpers/
ENTRYPOINT ["/app/.venv/bin/python", "-m", "pytest"]
CMD ["-q", "-p", "no:cacheprovider", "tests/test_transport_capture.py", "tests/test_capture_journal.py", "tests/test_local_collector.py", "tests/test_capture_checkpoint.py", "tests/test_capture_v3.py"]
