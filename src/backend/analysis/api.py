"""api.py - Service Layer of the Database & Analysis section (ONE door to our data)
Functions read persisted energy data through the database access layer.

@team the Dashboard and the AI Advisor call ONLY these functions and never the database
- building_id = an int from list_buildings()
- start, end = a date & time --> w/o a time zone = Berlin local time

- units: energy -> kWh | power -> kW | money -> EUR | CO2 -> kg
- times come back in Berlin local time
"""
from contextlib import closing

import pandas as pd

from backend import settings
from backend.analysis import calc
from backend.db import database
from backend.models import make_building
from backend.errors import AnalysisError, BuildingNotFoundError, RequestValidationError


# ---------- INTERNAL FUNCTIONS (@team DO NOT CALL THESE) ----------

def _local(ts):
    """make any time = Berlin time"""
    try:
        ts = pd.Timestamp(ts)
        if pd.isna(ts):
            raise ValueError('Missing timestamp')
        if ts.tzinfo is None:
            return ts.tz_localize(settings.LOCAL_TZ)
        return ts.tz_convert(settings.LOCAL_TZ)
    except (ValueError, TypeError, OverflowError) as exc:
        raise RequestValidationError('Use a valid ISO timestamp; include an offset for DST transitions') from exc


def _building(con, building_id):
    """Database row -> Home / Business / PublicBuilding object
        Unknown id -> ValueError
    """
    row = database.load_building(con, building_id)
    if row is None:
        raise BuildingNotFoundError(f"Unknown building id {building_id}")

    building_type = row["type"]
    name = row["name"]
    floor_area = row["floor_area_m2"]

    return make_building(building_type, name, floor_area)


def _readings(building_id, start, end):
    """-> (building, readings table in (local time: start, end))"""
    start = _local(start)
    end = _local(end)
    if start >= end:
        raise RequestValidationError(f"start ({start}) must be before end ({end})")

    # open database; 'closing' shuts it again automatically even after an error
    with closing(database.connect()) as con:
        building = _building(con, building_id)
        df = database.load_readings(con, building_id, start, end)

    # database times = UTC --> show them on Berlin clock
    df["ts"] = df["ts"].dt.tz_convert(settings.LOCAL_TZ)    # dt -> reach time functions of a whole column of times

    return building, df, start, end


def _energy(building_id, start, end):
    """-> sum(kWh per 15-min interval) of building with all zones from start to end"""
    building, df, start, end = _readings(building_id, start, end)

    # one row per zone per time -> add the zones together: one value at a time
    rows_by_time = df.groupby("ts")
    kwh = rows_by_time["value"].sum()

    return building, kwh, start, end


def _days(start, end):
    """Length of period in days"""
    duration = end - start
    one_day = pd.Timedelta(days=1)

    return (duration / one_day)





# ---------- CORE FUNCTIONS (@team USE THESE) ----------

# Which buildings exist
def list_buildings():
    """-> List of building dicts: id, name, type, floor_area_m2"""
    with closing(database.connect()) as con:
        buildings = database.list_buildings(con)

    return buildings


# What is happening right now (per zone)
def get_latest(building_id):
    """-> Newest reading time, total_power (kW) & power per zone"""
    # ONLY check if building exists
    with closing(database.connect()) as con:
        _building(con, building_id)

        # Ask for newest reading from last (incl) to last+15min (excl)
        last = database.latest_ts(con, building_id)
        if last is None:        # no readings yet -> empty answer, same shape
            return {
                "last_reading": None, 
                "power_kw": 0.0, 
                "zones": []
            }

        next_interval = last + pd.Timedelta("15min")
        df = database.load_readings(con, building_id, last, next_interval)

    # Find power for each zone
    zones = []
    for row in df.itertuples(): # loop over table row by row
        power = row.value * 4   # kWh in 15-min x 4 = kW
        zones.append({"zone": row.zone, "power_kw": round(power, 2)})

    # Find combined power from all zones
    total_power = 0
    for zone in zones:
        total_power += zone["power_kw"]

    last_berlin = last.tz_convert(settings.LOCAL_TZ)
    return {
        "last_reading": last_berlin.isoformat(),
        "power_kw": round(total_power, 2),
        "zones": zones,
    }


# How much energy, EUR, CO2 in a period (KPI = Key Performance Indicator)
def get_kpis(building_id, start, end):
    """-> dict of headline numbers for one building & period"""
    building, kwh, start, end = _energy(building_id, start, end)
    
    days = _days(start, end)
    energy = calc.total_kwh(kwh)

    prices = settings.CONFIG["prices"]
    eur_per_kwh = prices["eur_per_kwh"]
    co2_per_kwh = prices["co2_kg_per_kwh"]

    cost = calc.cost_eur(energy, eur_per_kwh)
    co2 = calc.co2_kg(energy, co2_per_kwh)

    readings_we_have = len(kwh)
    # completeness -> share of raw data used
    data_portion = calc.completeness(readings_we_have, days)

    # eui -> energy-use intensity (kWh per m2)
    eui = calc.eui_per_year(energy, building.floor_area_m2, days)
    
    return {
        "energy_kwh": energy,
        "cost_eur": cost,
        "co2_kg": co2,
        "eui_kwh_m2_yr": eui,
        "period_days": round(days, 2),
        "completeness": data_portion,
    }


# Energy per hour/day, one column per zone (data for chart plot)
def get_timeseries(building_id, start, end, freq="1h"):
    """-> table: one row per hour/day, one column per zone, kWh values"""
    if freq not in {'15min', '1h', '1D'}:
        raise RequestValidationError('freq must be 15min, 1h, or 1D')
    building, df, start, end = _readings(building_id, start, end)
    if df.empty:
        return pd.DataFrame(index=pd.DatetimeIndex([], tz=settings.LOCAL_TZ, name='ts'))

    # long table (ts, zone, value) -> wide table: one column per zone
    wide = df.pivot_table(index="ts", columns="zone", values="value", aggfunc="sum")   # aggfunc="sum" => if 2 rows land in same cell, add them

    # 15-min rows -> hourly/daily buckets (bucket w/o data = empty Not 0)
    # resample = turn 15-min rows into hourly rows + add values (if at least 1 value available)
    per_bucket = wide.resample(freq).sum(min_count=1)
     
    return per_bucket.round(3) 


# How much did we save comparing this period v/s the period (same length) just before
def get_savings(building_id, start, end):
    """-> energy_now vs energy_before (same period)"""
    # Energy of THIS period
    building, kwh_now, start, end = _energy(building_id, start, end)

    # period before (same length)
    length = end - start
    before_start = start - length

    # Energy of period BEFORE
    building, kwh_before, _, _ = _energy(building_id, before_start, start)


    # Totals & Difference
    energy_now = calc.total_kwh(kwh_now)
    energy_before = calc.total_kwh(kwh_before)
    energy_saved = round(energy_before - energy_now, 2)     # +ve = used less | -ve = used more
    change_percent = calc.change_pct(energy_now, energy_before)

    # Worth of saving
    prices = settings.CONFIG["prices"]
    saved_eur = calc.cost_eur(energy_saved, prices["eur_per_kwh"])
    saved_co2 = calc.co2_kg(energy_saved, prices["co2_kg_per_kwh"])

    return {
        "energy_kwh": energy_now,
        "previous_kwh": energy_before,
        "saved_kwh": energy_saved,
        "saved_eur": saved_eur,
        "saved_co2_kg": saved_co2,
        "change_pct": change_percent,
    }


# Sustainability score 0-100 and grade A-E
def get_score(building_id, start, end):
    """Sustainability score 0-100 & Grade A-E"""

    building, kwh, start, end = _energy(building_id, start, end)
    if kwh.empty:
        raise AnalysisError(f"No readings for building {building_id} in this period")

    # P1: Intensity
    energy = calc.total_kwh(kwh)
    days = _days(start, end)

    eui = calc.eui_per_year(energy, building.floor_area_m2, days)
    benchmark = settings.CONFIG["benchmarks"][building.building_type]   # e.g. "business" -> 100
    
    intensity = calc.intensity_points(eui, benchmark)


    # P2: After-hours
    energy_share, time_share = calc.after_hours(kwh, building.is_open)
    after_hours = calc.after_hours_points(energy_share, time_share)

    # Combine with the weights from config.toml
    parts = {"intensity": intensity, "after_hours": after_hours}
    weights = settings.CONFIG["score"]["weights"]
    score = calc.sustainability_score(parts, weights)

    grd = calc.grade(score)

    return {
        "score": score,
        "grade": grd,
        "intensity_points": intensity,
        "after_hours_points": after_hours,
        "eui_kwh_m2_yr": eui,
        "benchmark_kwh_m2_yr": benchmark,
        "after_hours_energy_share": round(energy_share, 3),
        "closed_time_share": round(time_share, 3),
    }



# Expected energy per hour for the next days
def get_forecast(building_id, days=7):
    """-> table: one row per future hour, column forecast_kwh"""

    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 30:
        raise RequestValidationError('Forecast days must be an integer between 1 and 30')
    # Find the newest reading (and check id exists)
    with closing(database.connect()) as con:
        _building(con, building_id)     # unknown id -> ValueError
        last = database.latest_ts(con, building_id)

    if last is None:
        raise AnalysisError(f"No readings for building {building_id}")

    # Load the last 4 weeks, up including newest reading
    four_weeks_ago = last - pd.Timedelta(weeks=4)
    just_after_last = last + pd.Timedelta("15min")  # end is excluded -> +15 min keeps 'last'
    building, kwh, _, _ = _energy(building_id, four_weeks_ago, just_after_last)

    # 15-min values -> hourly values (drop hours w/ no data -> avoid spoiling average)
    hourly = kwh.resample("1h").sum(min_count=1)
    hourly = hourly.dropna()


    forecast = calc.forecast_same_hour(hourly, days=days)

    # Series data -> one-column table
    return forecast.to_frame()


