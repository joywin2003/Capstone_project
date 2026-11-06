"""Explicit iterator and streaming CSV generator; no live meter is required."""

import csv
from datetime import datetime

from .events import EnergyEvent, StreamProcessingError


def csv_events(path):
    """Open the file only when consumed and close it when iteration finishes."""
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            for line, row in enumerate(csv.DictReader(handle), start=2):
                try:
                    if row["active"].lower() not in {"true", "false"}:
                        raise ValueError("active must be true or false")
                    yield EnergyEvent(
                        int(row["building_id"]), int(row["meter_id"]),
                        datetime.fromisoformat(row["timestamp"]),
                        float(row["energy_kwh"]), float(row["interval_minutes"]),
                        row["active"].lower() == "true",
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise StreamProcessingError(f"Invalid event on CSV line {line}") from exc
    except OSError as exc:
        raise StreamProcessingError("Cannot read energy event CSV") from exc


class HistoricalEnergyStream:
    def __init__(self, events):
        self._events = iter(events)

    @classmethod
    def from_csv(cls, path):
        return cls(csv_events(path))

    def __iter__(self):
        return self

    def __next__(self):
        event = next(self._events)
        if not isinstance(event, EnergyEvent):
            raise StreamProcessingError("Stream source must yield EnergyEvent objects")
        return event
