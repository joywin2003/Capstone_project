"""Run with ``python -m backend.streaming.demo`` after editable installation."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .events import StreamProcessingError
from .processors import ActiveMeterFilter, EnergyMetricsTransformer
from .source import HistoricalEnergyStream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path(__file__).parents[3] / "data/sample/energy_events.csv")
    parser.add_argument("--min-power", type=float, default=0.1)
    args = parser.parse_args()
    try:
        pipeline = ActiveMeterFilter(args.min_power) + EnergyMetricsTransformer()
        for result in pipeline.run(HistoricalEnergyStream.from_csv(args.csv)):
            print(json.dumps(asdict(result), default=str))
        print(f"received={pipeline.received} emitted={pipeline.emitted} dropped={pipeline.dropped}")
    except StreamProcessingError as exc:
        parser.exit(1, f"Stream error: {exc}\n")


if __name__ == "__main__":
    main()
