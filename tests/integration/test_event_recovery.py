"""Recovery across transactions, concurrent operators and independent processes."""

import json
import os
import subprocess
import sys
import threading
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
    StorageUnavailable,
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
    assert replay.generation == generation == result.generation + 1
    assert count(queue, probe_effects) == count(queue, receipts) == 1
    after = queue.inspect(result.delivery_id)
    assert [a["outcome"] for a in after["attempts"]] == ["apply", "duplicate"]
    assert after["replays"][0]["reason"] == "verify-deduplication"
    assert after["attempt_count"] == 1
    assert [a["generation"] for a in after["attempts"]] == [1, 2]
    assert [a["replay_generation"] for a in after["attempts"]] == [None, 2]
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
            == "0007_city_checkpoints"
        )


@pytest.mark.parametrize(
    "sql",
    [
        "DO $$ BEGIN RAISE EXCEPTION 'private database error' USING ERRCODE = '40001'; END $$",
        "SELECT pg_terminate_backend(pg_backend_pid())",
    ],
)
def test_database_failures_rollback_without_spending_handler_budget(store, wire, sql):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire)

    def fail_database(claim, transaction, payload):
        effect(transaction)
        transaction.connection.execute(text(sql))

    worker = EventWorker(queue, "location-v1", fail_database)
    for _ in range(4):
        with pytest.raises(StorageUnavailable):
            worker.step()
        row = queue.inspect(queue.list_deliveries("run-1")[0]["id"])
        assert row["status"] == "retry" and row["attempt_count"] == 0
        assert row["attempts"][-1]["outcome"] == "infrastructure-error"
        assert effects(queue) == count(queue, receipts) == 0
        assert "private database error" not in json.dumps(row, default=str)
        due(queue)
    worker.handler = lambda c, t, w: effect(t)
    assert worker.step().status == "apply"
    row = queue.inspect(row["id"])
    assert row["attempt_count"] == effects(queue) == count(queue, receipts) == 1
    assert len(row["attempts"]) == 5


def test_real_cross_context_deadlock_does_not_use_handler_budget(store, wire):
    queue = PostgresRecoveryStore(store.engine)
    with store.engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE deadlock_probe (id int PRIMARY KEY, value int NOT NULL)")
        )
        connection.execute(text("INSERT INTO deadlock_probe VALUES (1, 0), (2, 0)"))
    for context in ("run-a", "run-b"):
        publish(queue, wire, context=context)
    barrier = threading.Barrier(2)

    def collide(claim, transaction, payload):
        first = 1 if claim.context == "run-a" else 2
        transaction.connection.execute(
            text("UPDATE deadlock_probe SET value = value + 1 WHERE id = :id"), {"id": first}
        )
        barrier.wait(timeout=10)
        transaction.connection.execute(
            text("UPDATE deadlock_probe SET value = value + 1 WHERE id = :id"), {"id": 3 - first}
        )

    def step():
        try:
            return EventWorker(queue, "location-v1", collide).step().status
        except StorageUnavailable as error:
            assert error.__cause__.orig.sqlstate == "40P01"
            return "database-deadlock"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: step(), range(2)))
    assert sorted(results) == ["apply", "database-deadlock"]
    rows = queue.list_deliveries("run-a") + queue.list_deliveries("run-b")
    failed = next(row for row in rows if row["status"] == "retry")
    assert failed["attempt_count"] == 0
    due(queue)
    assert EventWorker(queue, "location-v1", lambda c, t, w: effect(t)).step().status == "apply"
    assert count(queue, receipts) == 2


def test_unrecordable_database_failure_is_reconciled_before_claiming_again(
    store, wire, monkeypatch
):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire)
    release = queue.release_infrastructure
    offline = True

    def unavailable(claim):
        if offline:
            raise StorageUnavailable("offline")
        return release(claim)

    monkeypatch.setattr(queue, "release_infrastructure", unavailable)

    def fail_database(claim, transaction, payload):
        transaction.connection.execute(
            text("DO $$ BEGIN RAISE EXCEPTION 'offline' USING ERRCODE = '40001'; END $$")
        )

    worker = EventWorker(queue, "location-v1", fail_database)
    with pytest.raises(StorageUnavailable):
        worker.step()
    claim = worker.interrupted_claim
    assert claim is not None
    with pytest.raises(StorageUnavailable):
        worker.step()
    assert count(queue, attempts) == 1
    expire(queue, claim)
    offline = False
    assert worker.step().status == "infrastructure-error"
    assert worker.interrupted_claim is None
    row = queue.inspect(claim.delivery_id)
    assert row["attempt_count"] == 0
    assert release(claim) == "infrastructure-error"
    assert queue.inspect(claim.delivery_id) == row
    due(queue)
    newer = queue.claim("location-v1")[0]
    with pytest.raises(StaleClaim):
        release(claim)
    assert queue.inspect(newer.delivery_id)["attempt_count"] == 1


def test_lost_completion_acknowledgement_does_not_refund_a_committed_effect(store, wire):
    class LostAcknowledgement(PostgresRecoveryStore):
        def complete(self, claim, handler):
            super().complete(claim, handler)
            raise StorageUnavailable("commit acknowledgement lost")

    queue = LostAcknowledgement(store.engine)
    publish(queue, wire)
    with pytest.raises(StorageUnavailable):
        EventWorker(queue, "location-v1", lambda c, t, w: effect(t)).step()
    row = queue.inspect(queue.list_deliveries("run-1")[0]["id"])
    assert row["status"] == "complete" and row["attempt_count"] == 1
    assert row["attempts"][0]["outcome"] == "apply"
    assert effects(queue) == count(queue, receipts) == 1


def test_replay_generations_link_each_retry_cycle_without_gaps(store, wire):
    queue = PostgresRecoveryStore(store.engine)
    publish(queue, wire)
    first = queue.claim("location-v1")[0]
    queue.fail(first, FailureCategory.INVALID)
    assert queue.replay(first.delivery_id, 1, ReplayReason.HANDLER_FIXED) == 2
    second = queue.claim("location-v1")[0]
    assert second.generation == 2
    queue.fail(second, FailureCategory.HANDLER)
    due(queue)
    third = queue.claim("location-v1")[0]
    assert third.generation == 3
    queue.complete(third, effect)
    assert queue.replay(first.delivery_id, 3, ReplayReason.VERIFY_DEDUPLICATION) == 4
    fourth = queue.claim("location-v1")[0]
    assert fourth.generation == 4
    assert queue.complete(fourth, effect).value == "duplicate"
    row = queue.inspect(first.delivery_id)
    assert [a["generation"] for a in row["attempts"]] == [1, 2, 3, 4]
    assert [a["replay_generation"] for a in row["attempts"]] == [None, 2, 2, 4]
    assert [r["generation"] for r in row["replays"]] == [2, 4]
    assert effects(queue) == 1
