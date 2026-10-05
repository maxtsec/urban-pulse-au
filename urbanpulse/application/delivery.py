"""Application delivery ports and atomic disposable projection handlers."""

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol

from urbanpulse.contracts.events import RevisionOutcome


class RetryableHandlerError(Exception):
    """A transient failure before any externally visible handler effect."""


class CompositionUnavailable(ValueError):
    """A bounded reconstruction could not finish; never serve its partial state."""


@dataclass(frozen=True)
class HandlerResult:
    outcome: str
    reason: str | None = None


class Handler(Protocol):
    name: str

    def handle(self, wire: str) -> HandlerResult: ...


class Publisher(Protocol):
    def publish(self, wire: str, handlers: Sequence[Handler]) -> dict[str, HandlerResult]: ...


class ProjectionHandler[State, Event]:
    def __init__(
        self,
        name: str,
        state: State,
        decode: Callable[[str], Event],
        apply: Callable[[State, Event], RevisionOutcome],
    ) -> None:
        self.name = name
        self.state = state
        self.decode = decode
        self.apply = apply

    def handle(self, wire: str) -> HandlerResult:
        try:
            event = self.decode(wire)
        except ValueError:
            return HandlerResult("rejected", "invalid-envelope")
        candidate = deepcopy(self.state)
        outcome = self.apply(candidate, event)
        # Counters, effects and receipts become visible in one pointer replacement.
        self.state = candidate
        if outcome == RevisionOutcome.CONFLICT:
            return HandlerResult("rejected", "conflict")
        return HandlerResult(
            {"apply": "applied", "duplicate": "duplicate", "superseded": "superseded"}[outcome]
        )


def revision_result(result: HandlerResult) -> RevisionOutcome:
    if result.outcome == "rejected":
        if result.reason == "conflict":
            return RevisionOutcome.CONFLICT
        raise CompositionUnavailable("published envelope was rejected")
    return {
        "applied": RevisionOutcome.APPLY,
        "duplicate": RevisionOutcome.DUPLICATE,
        "superseded": RevisionOutcome.SUPERSEDED,
    }[result.outcome]
