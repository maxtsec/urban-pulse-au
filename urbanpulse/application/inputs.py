"""Published normalized domain exports; raw provider bytes stay in capture adapters."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from urbanpulse.application.planning_replay import PlanningStep
from urbanpulse.application.weather_replay import WeatherStep
from urbanpulse.contracts.composition import TransportServiceStatusChanged

if TYPE_CHECKING:
    from urbanpulse.application.city import CapturedCity


@dataclass(frozen=True)
class CityInputs:
    captured: "CapturedCity"
    weather: tuple[WeatherStep, ...]
    planning: tuple[PlanningStep, ...]
    services: tuple[TransportServiceStatusChanged, ...] = ()

    def weather_at(self, seconds: int, outage: bool) -> tuple[WeatherStep, ...]:
        cutoff = self.captured.weather["outage_at_seconds"] if self.captured.weather else 0
        return tuple(
            step
            for step in self.weather
            if step.frame["at_seconds"] <= seconds
            and (step.frame["kind"] == "reading" or not outage or step.frame["at_seconds"] < cutoff)
        )

    def planning_at(self, seconds: int, outage: bool) -> tuple[PlanningStep, ...]:
        cutoff = self.captured.planning["outage_at_seconds"] if self.captured.planning else 0
        return tuple(
            step
            for step in self.planning
            if step.frame["at_seconds"] <= seconds
            and (not outage or step.frame["at_seconds"] < cutoff)
        )

    def read(self) -> "CapturedCity":
        return self.captured
