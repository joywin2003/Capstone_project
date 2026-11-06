"""opsd.py - loads the OPSD household dataset into our database
    RUN IT ONCE ->> Run: python -m backend.ingestion.opsd
"""

from contextlib import closing
from functools import wraps

import numpy as np
import pandas as pd

from backend import settings
from backend.db import database
from backend.models import EnergyMeter, Zone, make_building
from backend.errors import EnergyPlatformError, IngestionError


def ingestion_operation(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except EnergyPlatformError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise IngestionError(f'Cannot process energy data in {function.__name__}; check the input and configuration') from exc
    return wrapped


INTERVAL = pd.Timedelta("15min")    # Meters report their readings every 15min

# Turn big CSV data concerned to a table with time as row label
@ingestion_operation
def read_opsd(csv_path, columns):
    """Read only the columns we need; each value is a meter TOTAL (cumulative kWh)"""

    # columns we need: time column + one column per building
    # (from config.toml, columns = six meter columns ["DE_KN_residential1_grid_import",...]
    df = pd.read_csv(csv_path, usecols = ["utc_timestamp", *columns])
    ## *columns --> unpack into outer list 
    ##           => ["utc_timestamp", "DE_KN_residential1_grid_import",...] ELSE ["utc_timestamp", ["DE_KN_residential1_grid_import",...]]

    # Turn time text to real UTC time
    df["utc_timestamp"] = pd.to_datetime(df["utc_timestamp"], utc=True)

    # use the time as the row label instead of 0, 1, 2,...
    df = df.set_index("utc_timestamp")
    return df

# Meters provide the TOTAL ENERGY consumed
# -> need to find ENERGY USED in the 15 min intervals (between readings)
@ingestion_operation
def to_intervals(totals):
    """Meter Energy_Total -> kWh used in each 15 min interval"""
    # totals = table of total_energy
    if (not isinstance(totals.index, pd.DatetimeIndex) or totals.index.tz is None
            or not totals.index.is_unique or not totals.index.is_monotonic_increasing):
        raise IngestionError('Meter totals need unique, ordered, timezone-aware timestamps')
    totals = totals.dropna()    # .dropna() = remove empty cells

    # energy_used = total_energy - previous total_energy
    energy_used = totals.diff()

    # time between the two readings/totals
    times = totals.index.to_series()    ## totals.index -> row labels = times | .to_series() -> convert to columns as .diff() only works on that
    time_gap = times.diff()

    # ONLY trust the difference where gap is exactly 15 min
    is_one_step = time_gap == INTERVAL      # column of BOOL
    energy_used = energy_used[is_one_step]  # filter totals where only one 15 min interval


    # 10:15 total_energy - 10:00 total_energy = energy_used bet 10:00-10:15
    # New Label --> energy_used @ 10:00
    energy_used.index = energy_used.index - INTERVAL

    return energy_used



# VALIDATE DATA
# some buildings cannot exceed a certain energy maximum for their electrical network type and energy used needs to be positive
@ingestion_operation
def validate(used, max_kwh):
    """Keep only physically possible values | Returns (good values, number rejected)"""
    if not np.isfinite(max_kwh) or max_kwh <= 0:
        raise IngestionError('Maximum interval energy must be finite and positive')
    ok = np.isfinite(used) & (used >= 0) & (used <= max_kwh)
    good_values = used[ok]
    num_rejected = int((~ok).sum())
    return good_values, num_rejected


# Take a [[Building Block]] from config.toml and make it into real Python object (model.py)
@ingestion_operation
def build_from_config(entry):
    """one [[buildings]] entry from config.toml -> Building w/ 1 zone & 1 meter"""

    # settings.py - reads config.toml
    # [[buildings]] Block --> converted to dict {"name" : "Home 1", ...} --> entry

    # read the values from the config block
    building_type = entry["type"]
    name = entry["name"]
    floor_area = entry["floor_area_m2"]
    csv_column = entry["column"]                # data column from CSV file

    # Make building (Home, Business, PublicBuilding)
    building = make_building(building_type, name, floor_area)

    # FOR MVP --> one zone covering whole building | LATER VERSION --> multi-zones
    zone = Zone("Whole building")
    building.add_zone(zone)     # put zone into building

    # FOR MVP --> one meter per zone/building | LATER VERSION --> multiple meters
    meter = EnergyMeter(source=csv_column)      # create electricity meter & source = remember which CSV column data comes from
    zone.add_meter(meter)       # put meter into zone

    return building


# Clean Big raw table and give back 15-min Building Energy values
@ingestion_operation
def prepare(raw, entry, start, end):
    """Building's Column from CSV --> validated 15-min kWh between start (included) and end (excluded)"""
    # raw = CSV data
    # entry =
    #        [[buildings]] Block from config.toml --> converted to dict {"name" : "Home 1", ...} by settings.py --> entry

    # building's column of energy_totals
    column_name = entry["column"]
    totals = raw[column_name]       # extract meter readings

    # energy_totals --> 15-min interval energy_used
    energy_used = to_intervals(totals)

    # keep only the requested interval (start-inclusive to end-exclusive)
    # energy_used.index == UTC Time
    after_start = energy_used.index >= start    # BOOL table
    before_end = energy_used.index < end        # BOOL table

    energy_used = energy_used[after_start & before_end]


    # Highest realistic value for this type of building (from config.toml)
    building_type = entry["type"]
    all_limits = settings.CONFIG["validation"]["max_kwh_per_interval"]  # lookup the limit for this building type
    max_kwh = all_limits[building_type]

    # drop the unrealistic values
    good_values, num_rejected = validate(energy_used, max_kwh)

    return good_values, num_rejected


# Import dataset to database
def run():
    # import settings from config.toml
    data_settings = settings.CONFIG["data"]
    all_buildings = settings.CONFIG["buildings"]    # list of 6 dicts

    # date range = 01 Jan (incl) to 01 Dec (excl)
    start = pd.Timestamp(data_settings["start"], tz=settings.LOCAL_TZ)
    stop = pd.Timestamp(data_settings["replay_from"], tz=settings.LOCAL_TZ)

    # Read CSV for required columns
    csv_file = settings.ROOT / data_settings["csv_path"]
    columns_needed = []
    for entry in all_buildings:
        columns_needed.append(entry["column"])

    print(f"Reading {data_settings['csv_path']} ...")
    raw = read_opsd(csv_file, columns_needed)

    # Open database then handle each building
    with closing(database.connect()) as con:
        database.create_tables(con)

        for entry in all_buildings:
            building = build_from_config(entry)     # create building objects
            database.save_building(con, building)

            good_values, num_rejected = prepare(raw, entry, start, stop)

            meter = building.meters("electricity")[0]
            added = database.save_readings(con, meter.id, good_values)

            print(f"{building.name:<11} id={building.id} {added:6d} new readings {num_rejected} rejected")

    print("Done -> energy database")

# ONLY run the import when this file is started, not when imported
if __name__ == "__main__":
    try:
        run()
    except EnergyPlatformError as exc:
        raise SystemExit(f'Ingestion failed: {exc}') from exc

