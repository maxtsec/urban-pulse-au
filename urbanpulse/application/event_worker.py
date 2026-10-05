"""One fenced delivery per step; polling and process signals belong to the entry point."""

from collections.abc import Callable
from dataclasses import dataclass

from urbanpulse.application.durable_delivery import (
    DeliveryClaim,
    EventTransaction,
    FailureCategory,
    InvalidPublication,
    PublicationConflict,
    RecoveryStore,
    StaleClaim,
    StorageUnavailable,
)


@dataclass(frozen=True)
class WorkerResult:
    status: str
    delivery_id: str | None = None
    generation: int | None = None


class EventWorker:
    def __init__(
        self,
        store: RecoveryStore,
        consumer: str,
        handler: Callable[[DeliveryClaim, EventTransaction, str], None],
        *,
        lease_seconds: float = 30,
    ) -> None:
        self.store = store
        self.consumer = consumer
        self.handler = handler
        self.lease_seconds = lease_seconds
        self.interrupted_claim: DeliveryClaim | None = None

    def recover_infrastructure(self) -> WorkerResult:
        claim = self.interrupted_claim
        if claim is None:
            raise RuntimeError("no interrupted claim to reconcile")
        try:
            status = self.store.release_infrastructure(claim)
        except StaleClaim:
            status = "stale"
        # Storage failure propagates and leaves the claim pending for the next poll.
        self.interrupted_claim = None
        return WorkerResult(status, claim.delivery_id, claim.generation)

    def interrupted(self, claim: DeliveryClaim) -> None:
        self.interrupted_claim = claim
        try:
            self.recover_infrastructure()
        except StorageUnavailable:
            pass

    def step(self) -> WorkerResult:
        if self.interrupted_claim is not None:
            return self.recover_infrastructure()
        claims = self.store.claim(self.consumer, lease_seconds=self.lease_seconds)
        if not claims:
            return WorkerResult("idle")
        claim = claims[0]
        try:
            outcome = self.store.complete(
                claim, lambda transaction, wire: self.handler(claim, transaction, wire)
            )
            return WorkerResult(outcome.value, claim.delivery_id, claim.generation)
        except StorageUnavailable:
            self.interrupted(claim)
            raise
        except StaleClaim:
            return WorkerResult("stale", claim.delivery_id, claim.generation)
        except InvalidPublication:
            category = FailureCategory.INVALID
        except PublicationConflict:
            category = FailureCategory.CONFLICT
        except Exception:
            # Exception messages may contain connection strings, payloads or credentials.
            category = FailureCategory.HANDLER
        try:
            status = self.store.fail(claim, category)
        except StorageUnavailable:
            self.interrupted(claim)
            raise
        except StaleClaim:
            status = "stale"
        return WorkerResult(status, claim.delivery_id, claim.generation)
