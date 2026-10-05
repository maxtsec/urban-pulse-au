"""Atomic city run staging and reconstruction; event tables remain owned by the queue adapter."""

import json
from typing import Any

import psycopg
from sqlalchemy import select, update

from urbanpulse.adapters.city_run_tables import checkpoints, inbox, runs
from urbanpulse.adapters.city_store import CityInputStore, encode
from urbanpulse.adapters.event_recovery import PostgresRecoveryStore
from urbanpulse.adapters.event_store import PostgresEventTransaction, lock
from urbanpulse.application.capture_replay import payload_hash
from urbanpulse.application.city import SpatialMembership
from urbanpulse.application.city_checkpoints import (
    CONSUMER,
    RESULT_CONSUMER,
    RUN_VERSION,
    CheckpointPublisher,
    CityCheckpointModel,
    clocks,
)
from urbanpulse.application.composition import area_event, semantic_state
from urbanpulse.application.durable_delivery import (
    DeliveryClaim,
    EventTransaction,
    StorageUnavailable,
    receipt_from_wire,
    validate_key,
)


def context(run_id: str) -> str:
    validate_key(run_id)
    if len(run_id) > 100:
        raise ValueError("run ID exceeds 100 characters")
    return "city-run:" + run_id


class PostgresCityRuns:
    def __init__(
        self, queue: PostgresRecoveryStore, inputs: CityInputStore, spatial: SpatialMembership
    ) -> None:
        self.queue = queue
        self.inputs = inputs
        self.spatial = spatial

    def model(self, run: dict[str, Any]) -> CityCheckpointModel:
        inputs = self.inputs.load(run["scope"])
        model = CityCheckpointModel(inputs, self.spatial, run["scenario"])
        if (
            run["input_hash"] != payload_hash(json.loads(encode(inputs)))
            or run["boundary_revision"] != model.boundary_revision
            or run["rule_version"] != model.rule_version
            or run["run_version"] != RUN_VERSION
        ):
            raise ValueError("city run scope/version no longer matches its inputs")
        return model

    def create(self, run_id: str, scope: str, scenario: str) -> None:
        context(run_id)
        inputs = self.inputs.load(scope)
        model = CityCheckpointModel(inputs, self.spatial, scenario)
        identity = dict(
            id=run_id,
            scope=scope,
            scenario=scenario,
            input_hash=payload_hash(json.loads(encode(inputs))),
            boundary_revision=model.boundary_revision,
            rule_version=model.rule_version,
            run_version=RUN_VERSION,
        )
        with self.queue.transaction() as transaction:
            connection = transaction.connection
            lock(connection, "city-run", run_id)
            existing = (
                connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one_or_none()
            )
            if existing is not None:
                if any(existing[key] != value for key, value in identity.items()):
                    raise ValueError("run ID already pins another scope")
                return
            connection.execute(runs.insert().values(**identity))

    def read_run(self, run_id: str) -> dict[str, Any]:
        context(run_id)
        with self.queue.transaction() as transaction:
            row = (
                transaction.connection.execute(select(runs).where(runs.c.id == run_id))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise LookupError("unknown city run")
            return dict(row)

    def advance(self, run_id: str, target: int) -> None:
        model = self.model(self.read_run(run_id))
        values = clocks(model.inputs, target)
        # Preparation is read-only; publication and the monotonic cursor commit together below.
        plans = {value: model.plan(value) for value in values}
        with self.queue.transaction() as transaction:
            connection = transaction.connection
            lock(connection, "city-run", run_id)
            run = dict(
                connection.execute(select(runs).where(runs.c.id == run_id).with_for_update())
                .mappings()
                .one()
            )
            if target < run["target"]:
                raise ValueError("durable clock cannot rewind")
            existing = set(
                connection.execute(
                    select(checkpoints.c.seconds).where(checkpoints.c.run_id == run_id)
                ).scalars()
            )
            for value in values:
                if value not in existing and value > run["completed"]:
                    connection.execute(
                        checkpoints.insert().values(
                            run_id=run_id,
                            seconds=value,
                            status="scheduled",
                            manifest=encode(plans[value].wires),
                        )
                    )
            connection.execute(update(runs).where(runs.c.id == run_id).values(target=target))
            connection.execute(
                update(checkpoints)
                .where(checkpoints.c.run_id == run_id, checkpoints.c.status != "complete")
                .values(error=None)
            )
            self.activate(transaction, run)

    def activate(self, transaction: PostgresEventTransaction, run: dict[str, Any]) -> bool:
        connection = transaction.connection
        row = (
            connection.execute(
                select(checkpoints)
                .where(
                    checkpoints.c.run_id == run["id"],
                    checkpoints.c.status != "complete",
                )
                .order_by(checkpoints.c.seconds)
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["status"] != "scheduled" or row["error"] is not None:
            return False
        known = json.loads(run["publications"])
        last = run["last_publication"]
        required = []
        for wire in json.loads(row["manifest"]):
            publication = transaction.publish(context(run["id"]), wire, (CONSUMER,), after=last)
            required.append(publication)
            if publication not in known:
                known.append(publication)
                last = publication
        connection.execute(
            update(checkpoints)
            .where(
                checkpoints.c.run_id == run["id"],
                checkpoints.c.seconds == row["seconds"],
            )
            .values(status="pending", publications=encode(required))
        )
        connection.execute(
            update(runs)
            .where(runs.c.id == run["id"])
            .values(
                publications=encode(known),
                last_publication=last,
            )
        )
        return True

    def receive(self, claim: DeliveryClaim, transaction: EventTransaction, wire: str) -> None:
        if not isinstance(transaction, PostgresEventTransaction):
            raise TypeError("city inbox requires its PostgreSQL binding")
        if not claim.context.startswith("city-run:") or claim.consumer not in (
            CONSUMER,
            RESULT_CONSUMER,
        ):
            raise ValueError("unregistered city consumer context")
        run_id = claim.context.removeprefix("city-run:")
        event = receipt_from_wire(wire)
        transaction.connection.execute(
            inbox.insert().values(
                run_id=run_id,
                consumer=claim.consumer,
                source=event.source,
                event_id=event.event_id,
                envelope=wire,
            )
        )

    def progress(self) -> bool:
        with self.queue.transaction() as transaction:
            candidates = list(
                transaction.connection.execute(
                    select(runs.c.id).where(runs.c.completed < runs.c.target).order_by(runs.c.id)
                ).scalars()
            )
        for run_id in candidates:
            try:
                if self.finish(run_id):
                    return True
            except psycopg.Error as error:
                raise StorageUnavailable("spatial database unavailable") from error
        return False

    def finish(self, run_id: str) -> bool:
        with self.queue.transaction() as transaction:
            connection = transaction.connection
            lock(connection, "city-run", run_id)
            run = dict(
                connection.execute(select(runs).where(runs.c.id == run_id).with_for_update())
                .mappings()
                .one()
            )
            row = (
                connection.execute(
                    select(checkpoints)
                    .where(
                        checkpoints.c.run_id == run_id,
                        checkpoints.c.status != "complete",
                    )
                    .order_by(checkpoints.c.seconds)
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if row is None or row["error"] is not None:
                return False
            if row["status"] == "scheduled":
                return self.activate(transaction, run)
            if any(
                transaction.delivery_state(identity, CONSUMER) != "complete"
                for identity in json.loads(row["publications"])
            ):
                return False
            try:
                model = self.model(run)
                delivered = {
                    (item["source"], item["event_id"]): item["envelope"]
                    for item in connection.execute(
                        select(inbox).where(inbox.c.run_id == run_id, inbox.c.consumer == CONSUMER)
                    ).mappings()
                }
                view = model.evaluate(row["seconds"], CheckpointPublisher(delivered))
            except ValueError:
                connection.execute(
                    update(checkpoints)
                    .where(checkpoints.c.run_id == run_id, checkpoints.c.seconds == row["seconds"])
                    .values(error="checkpoint-reconstruction-unavailable")
                )
                return False
            semantic = encode(semantic_state(view))
            history = json.loads(run["area_events"])
            last_result = run["last_result_publication"]
            if semantic != run["semantic"]:
                event = area_event(view, len(history) + 1)
                last_result = transaction.publish(
                    context(run_id), event.model_dump_json(), (RESULT_CONSUMER,), after=last_result
                )
                history.append(event.model_dump(mode="json"))
            view["composition"].update(
                area_events=history, delivery="postgres-outbox", recovery="durable-city-checkpoint"
            )
            connection.execute(
                update(checkpoints)
                .where(
                    checkpoints.c.run_id == run_id,
                    checkpoints.c.seconds == row["seconds"],
                )
                .values(status="complete", result=encode(view))
            )
            connection.execute(
                update(runs)
                .where(runs.c.id == run_id)
                .values(
                    completed=row["seconds"],
                    semantic=semantic,
                    last_result_publication=last_result,
                    area_events=encode(history),
                )
            )
            run.update(completed=row["seconds"], semantic=semantic, area_events=encode(history))
            self.activate(transaction, run)
        return True

    def inspect(self, run_id: str, seconds: int | None = None) -> dict[str, Any]:
        context(run_id)
        with self.queue.transaction() as transaction:
            connection = transaction.connection
            connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            run = (
                connection.execute(select(runs).where(runs.c.id == run_id)).mappings().one_or_none()
            )
            if run is None:
                raise LookupError("unknown city run")
            rows = list(
                connection.execute(
                    select(checkpoints)
                    .where(checkpoints.c.run_id == run_id)
                    .order_by(checkpoints.c.seconds)
                ).mappings()
            )
            summary = []
            snapshot = None
            wanted = run["completed"] if seconds is None else seconds
            for row in rows:
                blocked = [
                    identity
                    for identity in json.loads(row["publications"])
                    if row["status"] == "pending"
                    and transaction.delivery_state(identity, CONSUMER) == "dead-letter"
                ]
                summary.append(
                    {
                        "seconds": row["seconds"],
                        "status": row["status"],
                        "error": row["error"],
                        "blocked_publications": blocked,
                    }
                )
                if row["seconds"] == wanted and row["status"] == "complete":
                    snapshot = json.loads(row["result"])
            return {
                "run_id": run_id,
                "scope": run["scope"],
                "scenario": run["scenario"],
                "target": run["target"],
                "completed": run["completed"],
                "checkpoints": summary,
                "snapshot": snapshot,
            }
