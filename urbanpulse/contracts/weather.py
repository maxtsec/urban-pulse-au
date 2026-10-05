"""Published weather fixture contracts; provider wire formats stay in adapters."""

from typing import Any, Literal, Self

from pydantic import Field, model_validator

from urbanpulse.contracts.events import CloudEvent, Identifier, Position, Timestamp, WireModel

PRODUCTS = frozenset({"severe-weather", "severe-thunderstorm", "riverine-flood", "flash-flood"})
LEVELS = frozenset({"Advice", "Watch and Act", "Emergency Warning"})


class WarningGeometry(WireModel):
    type: Literal["Polygon", "MultiPolygon"]
    # The spatial port validates topology after this structural check.
    coordinates: list[Any]

    @model_validator(mode="after")
    def valid_coordinates(self) -> Self:
        polygons = [self.coordinates] if self.type == "Polygon" else self.coordinates
        if not polygons:
            raise ValueError("warning geometry cannot be empty")
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError("a polygon needs rings")
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError("polygon rings must be closed with at least four points")
                for point in ring:
                    if not isinstance(point, list) or len(point) != 2:
                        raise ValueError("warning coordinates must be longitude/latitude pairs")
                    Position(longitude=point[0], latitude=point[1])
        return self


class WeatherWarning(WireModel):
    warning_id: Identifier
    level: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    description: str = Field(min_length=1)
    issued_at: Timestamp
    updated_at: Timestamp
    cancelled_at: Timestamp | None
    geometry: WarningGeometry | None
    spatial_precision: Literal["warning-polygon", "unknown"]
    source_url: str = Field(pattern=r"^https://emergency\.vic\.gov\.au/")

    @model_validator(mode="after")
    def valid_warning(self) -> Self:
        if self.updated_at < self.issued_at:
            raise ValueError("warning update cannot precede issue")
        if (
            self.cancelled_at is not None
            and not self.issued_at <= self.cancelled_at <= self.updated_at
        ):
            raise ValueError("cancellation must fall between issue and update")
        if (self.geometry is None) != (self.spatial_precision == "unknown"):
            raise ValueError("geometry and spatial precision disagree")
        return self


class WeatherWarningChanged(CloudEvent[WeatherWarning]):
    type: Literal["au.urbanpulse.weather.warning-changed.v1"]

    @model_validator(mode="after")
    def consistent_warning(self) -> Self:
        provenance = self.data.provenance
        expected = f"{provenance.provider}/{provenance.product}/{provenance.record_id}"
        if self.subject != expected or self.subject != self.data.state.warning_id:
            raise ValueError("warning identity must include provider/product/record")
        if not self.source.endswith(":weather") or not provenance.capture_ids:
            raise ValueError("weather owner and capture provenance are required")
        if self.data.effective_from is None or self.data.effective_until is None:
            raise ValueError("fixture warnings require explicit validity")
        if provenance.source_observed_at != self.data.state.updated_at:
            raise ValueError("warning update and provenance source times must agree")
        if self.data.state.updated_at > self.time:
            raise ValueError("warning cannot be accepted before its update")
        return self


class ModelledReading(WireModel):
    reading_id: Identifier
    model: Identifier
    valid_at: Timestamp
    position: Position
    temperature_c: float = Field(strict=True)
    precipitation_mm: float = Field(strict=True, ge=0)
    wind_kmh: float = Field(strict=True, ge=0)
    source_url: Literal["https://open-meteo.com/"]
    kind: Literal["modelled"]


class ModelledReadingChanged(CloudEvent[ModelledReading]):
    type: Literal["au.urbanpulse.weather.modelled-reading-changed.v1"]

    @model_validator(mode="after")
    def consistent_reading(self) -> Self:
        provenance = self.data.provenance
        expected = f"{provenance.provider}/{provenance.product}/{provenance.record_id}"
        if (
            self.subject != expected
            or self.subject != self.data.state.reading_id
            or not self.source.endswith(":weather")
        ):
            raise ValueError("reading owner and provider/product/record identity must agree")
        if (
            provenance.source_observed_at != self.data.state.valid_at
            or self.data.state.valid_at > self.time
        ):
            raise ValueError("fixture modelled source time must match validity and precede receipt")
        if not self.data.provenance.capture_ids:
            raise ValueError("reading capture provenance is required")
        if (
            self.data.effective_from != self.data.state.valid_at
            or self.data.effective_until is not None
        ):
            raise ValueError("modelled validity must match its point in time")
        return self
