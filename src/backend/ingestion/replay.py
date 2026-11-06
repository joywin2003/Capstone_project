"""Replay historical OPSD intervals, persist all valid energy, and emit filtered insights."""

from contextlib import closing
import time

import pandas as pd

from backend import settings
from backend.errors import EnergyPlatformError, StreamProcessingError
from backend.db import database
from backend.ingestion import opsd
from backend.streaming.events import EnergyEvent
from backend.streaming.processors import ActiveMeterFilter, EnergyMetricsTransformer
from backend.streaming.source import HistoricalEnergyStream


def run(pause=None):
    data = settings.CONFIG['data']
    pause = data['replay_seconds'] if pause is None else pause
    if pause < 0:
        raise StreamProcessingError('Replay pause must be nonnegative')
    entries = settings.CONFIG['buildings']
    start = pd.Timestamp(data['replay_from'], tz=settings.LOCAL_TZ)
    end = pd.Timestamp(data['end'], tz=settings.LOCAL_TZ)
    raw = opsd.read_opsd(settings.ROOT / data['csv_path'], [e['column'] for e in entries])
    prices = settings.CONFIG['prices']
    pipeline = ActiveMeterFilter(0.1) + EnergyMetricsTransformer(
        prices['eur_per_kwh'], prices['co2_kg_per_kwh'])
    with closing(database.connect()) as con:
        database.create_tables(con)
        upcoming = {}
        for entry in entries:
            building = opsd.build_from_config(entry)
            database.save_building(con, building)
            values, rejected = opsd.prepare(raw, entry, start, end)
            print(f'{building.name}: {rejected} invalid intervals rejected')
            upcoming[building.meters()[0].id] = (building.id, values)
        stamps = sorted({ts for _, values in upcoming.values() for ts in values.index})
        last = database.latest_ts(con)
        if last is not None:
            stamps = [ts for ts in stamps if ts >= last]

        def events():
            for ts in stamps:
                for meter_id, (building_id, values) in upcoming.items():
                    if ts in values.index:
                        # Persist all valid readings. Usage filtering is only for insights.
                        database.save_readings(con, meter_id, values.loc[[ts]])
                        yield EnergyEvent(building_id, meter_id, ts.to_pydatetime(), float(values.loc[ts]))
                time.sleep(pause)

        print(f'Replaying {len(stamps)} historical intervals; Ctrl+C to stop.')
        try:
            for result in pipeline.run(HistoricalEnergyStream(events())):
                print(f'{result.event.timestamp.isoformat()} meter={result.event.meter_id} '
                      f'{result.power_kw:.3f} kW EUR {result.cost_eur:.4f} '
                      f'{result.co2_kg:.4f} kg CO2')
        except KeyboardInterrupt:
            print('Replay stopped')
        finally:
            print(f'received={pipeline.received} emitted={pipeline.emitted} dropped={pipeline.dropped}')


if __name__ == '__main__':
    try:
        run()
    except EnergyPlatformError as exc:
        raise SystemExit(f'Replay failed: {exc}') from exc
