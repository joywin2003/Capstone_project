"""Polymorphic processors composed with ``filter_stage + transform_stage``."""

from abc import ABC, abstractmethod
from math import isfinite

from .events import EnergyEvent, EnergyResult, StreamProcessingError


class StreamProcessor(ABC):
    @abstractmethod
    def process(self, event):
        """Return an event/result, or None to deliberately drop the event."""

    def __add__(self, other):
        if not isinstance(other, StreamProcessor):
            return NotImplemented
        return Pipeline((self, other))


class Pipeline(StreamProcessor):
    def __init__(self, stages):
        self.stages = tuple(stages)
        if not self.stages or not all(isinstance(s, StreamProcessor) for s in self.stages):
            raise StreamProcessingError("A pipeline needs StreamProcessor stages")
        self.received = self.emitted = self.dropped = 0

    def __add__(self, other):
        if not isinstance(other, StreamProcessor):
            return NotImplemented
        stages = other.stages if isinstance(other, Pipeline) else (other,)
        return Pipeline(self.stages + stages)

    def process(self, event):
        self.received += 1
        for stage in self.stages:
            event = stage.process(event)
            if event is None:
                self.dropped += 1
                return None
        self.emitted += 1
        return event

    def run(self, events):
        """A lazy generator: no input is consumed before the first next()."""
        for event in events:
            result = self.process(event)
            if result is not None:
                yield result


class ActiveMeterFilter(StreamProcessor):
    def __init__(self, min_power_kw=0.1):
        if not isinstance(min_power_kw, (int, float)) or not isfinite(min_power_kw) or min_power_kw < 0:
            raise StreamProcessingError("Minimum power must be finite and nonnegative")
        self.min_power_kw = min_power_kw

    def process(self, event):
        if not isinstance(event, EnergyEvent):
            raise StreamProcessingError("The filter requires an EnergyEvent")
        return event if event.active and event.power_kw >= self.min_power_kw else None


class EnergyMetricsTransformer(StreamProcessor):
    def __init__(self, eur_per_kwh=0.30, kg_co2_per_kwh=0.38):
        if any(not isinstance(x, (int, float)) or not isfinite(x) or x < 0 for x in (eur_per_kwh, kg_co2_per_kwh)):
            raise StreamProcessingError("Tariff and emissions factor must be finite/nonnegative")
        self.eur_per_kwh = eur_per_kwh
        self.kg_co2_per_kwh = kg_co2_per_kwh

    def process(self, event):
        if not isinstance(event, EnergyEvent):
            raise StreamProcessingError("The transformer requires an EnergyEvent")
        return EnergyResult(event, event.power_kw,
                            round(event.energy_kwh * self.eur_per_kwh, 4),
                            round(event.energy_kwh * self.kg_co2_per_kwh, 4))
