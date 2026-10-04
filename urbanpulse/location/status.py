"""Explain current area conditions independently of source coverage."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CoverageState(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class Condition(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


def require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")


@dataclass(frozen=True)
class Coverage:
    input_id: str
    state: CoverageState


@dataclass(frozen=True)
class AdverseFact:
    """An already accepted, spatially applicable fact from a domain contract."""

    id: str
    input_id: str
    reason: str
    effective_from: datetime
    effective_until: datetime | None = None
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        require_aware(self.effective_from)
        if self.effective_until is not None:
            require_aware(self.effective_until)
            if self.effective_until <= self.effective_from:
                raise ValueError("effective_until must be after effective_from")
        if self.resolved_at is not None:
            require_aware(self.resolved_at)
            if self.resolved_at < self.effective_from:
                raise ValueError("resolved_at must not precede effective_from")

    def active_at(self, at: datetime) -> bool:
        require_aware(at)
        return (
            self.effective_from <= at
            and (self.effective_until is None or at < self.effective_until)
            and (self.resolved_at is None or at < self.resolved_at)
        )


@dataclass(frozen=True)
class AreaAssessment:
    condition: Condition
    reasons: tuple[AdverseFact, ...]
    coverage: tuple[Coverage, ...]
    incomplete_inputs: tuple[str, ...]
    evaluated_at: datetime


def assess_area(
    *,
    facts: tuple[AdverseFact, ...],
    coverage: tuple[Coverage, ...],
    required_inputs: frozenset[str],
    at: datetime,
) -> AreaAssessment:
    """Consume accepted evidence; do not infer provider validity or spatial matches."""
    require_aware(at)
    if not required_inputs:
        raise ValueError("a normal claim requires an explicit nonempty input policy")
    by_input = {entry.input_id: entry.state for entry in coverage}
    if len(by_input) != len(coverage):
        raise ValueError("coverage input IDs must be unique")
    if len({fact.id for fact in facts}) != len(facts):
        raise ValueError("fact IDs must be unique within the assessment")
    if any(fact.input_id not in by_input for fact in facts):
        raise ValueError("every fact must have explicit source coverage")
    if any(fact.input_id not in required_inputs for fact in facts):
        raise ValueError("facts must belong to required current-condition inputs")
    incomplete = tuple(
        sorted(key for key in required_inputs if by_input.get(key) != CoverageState.CURRENT)
    )
    active = tuple(sorted((fact for fact in facts if fact.active_at(at)), key=lambda fact: fact.id))
    if active:
        condition = Condition.DEGRADED
    elif incomplete:
        condition = Condition.UNKNOWN
    else:
        condition = Condition.NORMAL
    ordered_coverage = tuple(sorted(coverage, key=lambda entry: entry.input_id))
    return AreaAssessment(condition, active, ordered_coverage, incomplete, at)
