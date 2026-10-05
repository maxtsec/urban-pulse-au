"""One registry for supported fixture scenarios and their domain capabilities."""

from dataclasses import dataclass
from enum import StrEnum


class Scenario(StrEnum):
    JOURNEY = "journey"
    EMPTY = "empty"
    OUTAGE = "outage"
    WEATHER = "weather"
    WEATHER_OUTAGE = "weather-outage"
    CITY = "city"
    PLANNING_OUTAGE = "planning-outage"


@dataclass(frozen=True)
class ScenarioPolicy:
    weather: bool = False
    planning: bool = False
    weather_outage: bool = False
    planning_outage: bool = False


SCENARIOS = {
    Scenario.JOURNEY: ScenarioPolicy(),
    Scenario.EMPTY: ScenarioPolicy(),
    Scenario.OUTAGE: ScenarioPolicy(),
    Scenario.WEATHER: ScenarioPolicy(weather=True),
    Scenario.WEATHER_OUTAGE: ScenarioPolicy(weather=True, weather_outage=True),
    Scenario.CITY: ScenarioPolicy(weather=True, planning=True),
    Scenario.PLANNING_OUTAGE: ScenarioPolicy(weather=True, planning=True, planning_outage=True),
}


def scenario_policy(value: str) -> ScenarioPolicy:
    return SCENARIOS[Scenario(value)]
