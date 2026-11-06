"""Deterministic demo data; synthetic interval readings, not measured properties."""

from contextlib import closing

import pandas as pd

from backend.db import database
from backend.models import EnergyMeter, Zone, make_building


def initialize(url=None, sample=False):
    token = database.DATABASE_OVERRIDE.set(url or database.configured_url())
    try:
        with closing(database.connect()) as con:
            database.create_tables(con)
            if sample:
                for name, kind, area, value in [('Demo Home', 'home', 140, 0.5),
                                                 ('Demo Office', 'business', 2500, 2.0)]:
                    building = make_building(kind, name, area)
                    meter = EnergyMeter(source='synthetic-demo')
                    building.add_zone(Zone('Whole building')).add_meter(meter)
                    database.save_building(con, building)
                    values = pd.Series(value, index=pd.date_range('2016-12-01', periods=96, freq='15min', tz='UTC'))
                    database.save_readings(con, meter.id, values)
    finally:
        database.DATABASE_OVERRIDE.reset(token)
