"""Recovery across transactions, concurrent operators and independent processes."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from test_event_store import count, effect, effects, expire, publish
from test_event_store import store as store
from test_event_store import wire as wire

from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.event_tables import (
    attempts,
    deliveries,
    probe_effects,
    publications,
    receipts,
)
from urbanpulse.adapters.recovery_probe import CONSUMER, apply_probe
from urbanpulse.application.durable_delivery import (
    FailureCategory,
    PublicationConflict,
    ReplayReason,
    StaleClaim,
)
from urbanpulse.application.event_worker import EventWorker

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[2]


def due(store):
    with store.engine.begin() as connection:
        connection.execute(
            update(deliveries)
            .where(deliveries.c.status == "retry")
            .values(available_at=text("clock_timestamp() - interval '1 second'"))
        )


def test_worker_replay_keeps_effect_original_wire_and_attempt_history(store, wire):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire, (CONSUMER,))
    worker = EventWorker(queue, CONSUMER, apply_probe)
    result = worker.step()
    assert result.status == "apply"
    before = queue.inspect(result.delivery_id)
    assert before["status"] == "complete"
    generation = queue.replay(
        result.delivery_id, result.generation, ReplayReason.VERIFY_DEDUPLICATION
    )
    assert generation > result.generation
    replay = worker.step()
    assert replay.status == "duplicate"
    assert count(queue, probe_effects) == count(queue, receipts) == 1
    after = queue.inspect(result.delivery_id)
    assert [a["outcome"] for a in after["attempts"]] == ["apply", "duplicate"]
    assert after["replays"][0]["reason"] == "verify-deduplication"
    assert after["attempt_count"] == 1
    with queue.engine.connect() as connection:
        assert connection.execute(select(publications.c.envelope)).scalar_one() == wire
    with pytest.raises(StaleClaim):
        queue.replay(result.delivery_id, result.generation, ReplayReason.OPERATOR_RETRY)
    assert queue.metrics(CONSUMER)["backlog_count"] == 0


def test_retry_schedule_and_budget_survive_repository_restart_and_rollback_effects(store, wire):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire)

    def failing(claim, transaction, payload):
        effect(transaction)
        raise RuntimeError("SECRET credential must never be persisted")

    for attempt, delay in ((1, 1), (2, 5), (3, None)):
        queue = PostgresRecoveryStore(store.engine)
        result = EventWorker(queue, "location-v1", failing).step()
        row = queue.inspect(result.delivery_id)
        assert row["attempt_count"] == attempt
        assert row["status"] == ("retry" if delay else "dead-letter")
        assert row["outcome"] == "handler-error"
        assert "SECRET" not in json.dumps(row, default=str)
        assert effects(queue) == count(queue, receipts) == 0
        if delay:
            assert (row["available_at"] - row["attempts"][-1]["ended_at"]).total_seconds() == delay
            assert PostgresRecoveryStore(store.engine).claim("location-v1") == ()
            assert queue.metrics("location-v1")["retry_count"] == 1
            due(queue)
    assert count(queue, attempts) == 3
    assert queue.metrics("location-v1")["dead_letter_count"] == 1
    queue.replay(result.delivery_id, result.generation, ReplayReason.HANDLER_FIXED)
    assert EventWorker(queue, "location-v1", lambda c, t, w: effect(t)).step().status == "apply"
    assert effects(queue) == count(queue, receipts) == 1
    assert count(queue, attempts) == 4


@pytest.mark.parametrize("wire_value", ["not json", None])
def test_invalid_stored_envelope_is_terminal_without_handler_or_retry(store, wire, wire_value):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire)
    with queue.engine.begin() as connection:
        if wire_value is None:
            connection.execute(update(publications).values(fingerprint="0" * 64))
        else:
            connection.execute(update(publications).values(envelope=wire_value))
    result = EventWorker(
        queue, "location-v1", lambda *_: pytest.fail("invalid event applied")
    ).step()
    row = queue.inspect(result.delivery_id)
    assert result.status == "dead-letter" and row["outcome"] == "invalid-envelope"
    assert len(row["attempts"]) == 1
    assert queue.claim("location-v1") == ()


def test_handler_value_error_retries_but_publication_conflict_is_terminal(store, wire):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire)

    def handler(*_):
        raise ValueError("domain handler failure")

    assert EventWorker(queue, "location-v1", handler).step().status == "retry"
    due(queue)

    def conflict(*_):
        raise PublicationConflict("derived identity changed")

    result = EventWorker(queue, "location-v1", conflict).step()
    assert result.status == "dead-letter"
    assert queue.inspect(result.delivery_id)["outcome"] == "publication-conflict"


def test_failure_recording_is_idempotent_and_rejects_stale_identity(store, wire):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire)
    claim = queue.claim("location-v1")[0]
    assert queue.fail(claim, FailureCategory.HANDLER) == "retry"
    first = queue.inspect(claim.delivery_id)
    assert queue.fail(claim, FailureCategory.HANDLER) == "retry"
    assert queue.inspect(claim.delivery_id) == first
    for altered in (
        replace(claim, context="wrong"),
        replace(claim, consumer="wrong"),
        replace(claim, generation=99),
    ):
        with pytest.raises(StaleClaim):
            queue.fail(altered, FailureCategory.HANDLER)
    due(queue)
    current = queue.claim("location-v1")[0]
    with pytest.raises(StaleClaim):
        queue.fail(claim, FailureCategory.HANDLER)
    expire(queue, current)
    with pytest.raises(StaleClaim):
        queue.fail(current, FailureCategory.HANDLER)


def test_expired_lease_is_scheduled_from_deadline_not_worker_restart_time(store, wire):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire)
    claim = queue.claim("location-v1")[0]
    with queue.engine.begin() as connection:
        connection.execute(
            update(deliveries).values(
                lease_until=text("clock_timestamp() - interval '0.1 seconds'")
            )
        )
    assert queue.claim("location-v1") == ()
    row = queue.inspect(claim.delivery_id)
    assert row["status"] == "retry" and row["outcome"] == "lease-expired"
    assert row["attempt_count"] == 1
    due(queue)
    new = queue.claim("location-v1")[0]
    assert new.generation == 2


def test_concurrent_replay_operators_cannot_reset_budget_twice(store, wire):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire)
    claim = queue.claim("location-v1")[0]
    with pytest.raises(StaleClaim):
        queue.replay(claim.delivery_id, claim.generation, ReplayReason.OPERATOR_RETRY)
    queue.fail(claim, FailureCategory.INVALID)

    def replay():
        try:
            return queue.replay(claim.delivery_id, claim.generation, ReplayReason.OPERATOR_RETRY)
        except StaleClaim:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: replay(), range(2)))
    assert outcomes.count("stale") == 1
    assert len(queue.inspect(claim.delivery_id)["replays"]) == 1


def cli(store, *args):
    env = dict(
        os.environ,
        DATABASE_URL=store.engine.url.render_as_string(hide_password=False),
        PYTHONPATH=str(ROOT),
    )
    return subprocess.run(
        [sys.executable, "-m", "workers.events.main", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_real_cli_seed_run_inspect_replay_and_metrics(store):
    queue = PostgresRecoveryStore(store.engine)
    seeded = cli(queue, "seed-probe", "--context", "cli-recovery")
    assert seeded.returncode == 0, seeded.stderr
    first = json.loads(cli(queue, "run", "--once").stdout)
    assert first["status"] == "apply"
    inspected = json.loads(cli(queue, "inspect", first["delivery_id"]).stdout)
    assert inspected["status"] == "complete"
    replayed = cli(
        queue,
        "replay",
        first["delivery_id"],
        "--generation",
        str(first["generation"]),
        "--reason",
        "verify-deduplication",
    )
    assert replayed.returncode == 0
    assert json.loads(cli(queue, "run", "--once").stdout)["status"] == "duplicate"
    assert count(queue, probe_effects) == 1
    assert json.loads(cli(queue, "metrics").stdout)["backlog_count"] == 0
    assert len(json.loads(cli(queue, "list", "--context", "cli-recovery").stdout)) == 1


@pytest.mark.parametrize("stage", ["claimed", "effect-written", "committed"])
def test_process_termination_and_restart_preserve_exactly_one_database_effect(store, wire, stage):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire, (CONSUMER,))
    env = dict(
        os.environ,
        DATABASE_URL=store.engine.url.render_as_string(hide_password=False),
        PYTHONPATH=str(ROOT),
    )
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "tests/helpers/event_worker_process.py"), stage],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        assert pool.submit(process.stdout.readline).result(timeout=15).strip() == stage
        process.kill()
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        pool.shutdown(wait=True)
        process.stdout.close()
        process.stderr.close()
    row = queue.list_deliveries("run-1")[0]
    if stage == "committed":
        assert count(queue, probe_effects) == 1
        queue.replay(row["id"], row["generation"], ReplayReason.VERIFY_DEDUPLICATION)
        expected = "duplicate"
    else:
        assert count(queue, probe_effects) == count(queue, receipts) == 0
        with queue.engine.begin() as connection:
            connection.execute(
                update(deliveries).values(
                    lease_until=text("clock_timestamp() - interval '10 seconds'")
                )
            )
        expected = "apply"
    recovered = cli(queue, "run", "--once")
    assert recovered.returncode == 0, recovered.stderr
    assert json.loads(recovered.stdout)["status"] == expected
    assert count(queue, probe_effects) == count(queue, receipts) == 1
    assert len(queue.inspect(row["id"])["attempts"]) == 2


def test_continuous_worker_polls_and_handles_work_without_restarting(store, wire):
    queue = PostgresRecoveryStore(store.engine)
    env = dict(
        os.environ,
        DATABASE_URL=store.engine.url.render_as_string(hide_password=False),
        PYTHONPATH=str(ROOT),
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "workers.events.main", "run", "--poll-seconds", "0.05"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        for context in ("first-run", "second-run"):
            publish(queue, wire, (CONSUMER,), context=context)
            result = json.loads(pool.submit(process.stdout.readline).result(timeout=15))
            assert result["status"] == "apply"
        assert count(queue, probe_effects) == 2
        if os.name != "nt":
            process.terminate()
            assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        pool.shutdown(wait=True)
        process.stdout.close()
        process.stderr.close()


@pytest.mark.parametrize("retained", ["retry", "probe", "replay"])
def test_downgrade_refuses_to_erase_recovery_state(store, wire, retained):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire, (CONSUMER,))
    claim = queue.claim(CONSUMER)[0]
    if retained == "retry":
        queue.fail(claim, FailureCategory.HANDLER)
    elif retained == "probe":
        queue.complete(claim, lambda transaction, payload: apply_probe(claim, transaction, payload))
    else:
        queue.fail(claim, FailureCategory.INVALID)
        queue.replay(claim.delivery_id, claim.generation, ReplayReason.OPERATOR_RETRY)
    before = queue.inspect(claim.delivery_id)
    config = Config()
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = store.engine.url.render_as_string(hide_password=False)
    with pytest.raises(DBAPIError, match="recovery data prevents downgrade"):
        command.downgrade(config, "0005_attempt_policy")
    assert queue.inspect(claim.delivery_id) == before
    with store.engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == "0006_worker_recovery"
        )
