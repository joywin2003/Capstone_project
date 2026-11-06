"""Immutable event contracts. Energy is per interval, never a cumulative total."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


class StreamProcessingError(ValueError):
    """An event or a processor configuration is invalid."""


@dataclass(frozen=True)
class EnergyEvent:
    building_id: int
    meter_id: int
    timestamp: datetime
    energy_kwh: float
    interval_minutes: float = 15
    active: bool = True

    def __post_init__(self):
        if not isinstance(self.timestamp, datetime) or self.timestamp.utcoffset() is None:
            raise StreamProcessingError("Event timestamp must include a timezone")
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
               for value in (self.building_id, self.meter_id)):
            raise StreamProcessingError("Building and meter IDs must be positive integers")
        if not isinstance(self.active, bool):
            raise StreamProcessingError("active must be a boolean")
        try:
            valid = (isfinite(self.energy_kwh) and self.energy_kwh >= 0
                     and isfinite(self.interval_minutes) and self.interval_minutes > 0)
        except TypeError as exc:
            raise StreamProcessingError("Energy and duration must be numeric") from exc
        if not valid:
            raise StreamProcessingError("Energy must be finite/nonnegative and duration positive")

    @property
    def power_kw(self):
        return self.energy_kwh * 60 / self.interval_minutes


@dataclass(frozen=True)
class EnergyResult:
    event: EnergyEvent
    power_kw: float
    cost_eur: float
    co2_kg: float
