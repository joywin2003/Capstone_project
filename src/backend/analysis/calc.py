"""calc.py - The Mathematical Analysis"""

import numpy as np
import pandas as pd

from backend.errors import AnalysisError

def total_kwh(kwh):
    """Sum all 15-min energy values -> total kWh (2 d.p)"""
    total = kwh.sum()
    total = float(total)        # numpy num --> plain Python num

    return round(total, 2)


def cost_eur(energy_kwh, eur_per_kwh):
    """Energy x price -> cost in EUR (2 d.p)"""
    cost = energy_kwh * eur_per_kwh

    return round(cost, 2)


def co2_kg(energy_kwh, kg_per_kwh):
    """Energy x grid emission factor -> kg pf CO2 (1 d.p)"""
    co2 = energy_kwh * kg_per_kwh

    return round(co2, 1)


def completeness(n_readings, period_days, interval_min=15):
    """Share of reading are really using (- rejected)"""
    if (not all(np.isfinite(x) for x in (n_readings, period_days, interval_min))
            or n_readings < 0 or period_days < 0 or interval_min <= 0):
        raise AnalysisError('Completeness needs nonnegative counts/period and a positive interval')
    minutes_in_period = period_days * 24 * 60
    expected_readings = minutes_in_period / interval_min

    if expected_readings == 0:
        return 0.0  # avoid zero division

    share = n_readings / expected_readings
    return round(share, 3)


def eui_per_year(energy_kwh, floor_area_m2, period_days):
    """Energy Use Intensity (EUI)"""

    if any(not np.isfinite(x) for x in (energy_kwh, floor_area_m2, period_days)) or floor_area_m2 <= 0 or period_days <= 0:
        raise AnalysisError('Floor area and period must be finite and positive')
    kwh_per_m2 = energy_kwh / floor_area_m2

    scale_to_year = 365 / period_days

    eui = kwh_per_m2 * scale_to_year

    return round(eui, 1)


# How much energy used while building is closed
def after_hours(kwh, is_open):
    """-> energy_share used while closed, time_share while closed"""

    # for every 15-min time, ask building if open
    open_flags = []
    for ts in kwh.index:
        open_flags.append(is_open(ts))  # BOOL list -> TRUE = open
    open_flags = np.array(open_flags, dtype=bool)

    # flip flags so TRUE = building closed
    closed = ~open_flags

    # Energy_Share when closed
    total_energy = kwh.sum()
    if total_energy == 0:
        energy_share = 0.0  # avoid zero division if no energy used

    else:
        closed_energy = kwh[closed].sum()   # sum of energy used when closed
        energy_share = float(closed_energy / total_energy)

    # Share of Time building closed
    if len(closed) == 0:
        time_share = 0.0    # avoid zero division

    else:
        time_share = float(closed.mean())   # time_closed / total_time = steps_closed / total_steps = mean steps_closed

    return energy_share, time_share


def clamp(points):
    """Keep points between 0 and 100"""
    if points < 0:
        points = 0.0
    if points > 100:
        points = 100.0

    return round(points, 1)


# Sustainability score P1: Intensity 
# --> How efficient is the building per m2
def intensity_points(eui_year, benchmark):
    """I = clamp(100 * (1.5 - EUI / B))
        ( EUI <= 0.5 B : 100 pts | EUI == B : 50 pts | EUI >= 1.5 B : 0 pts)
    """

    if not np.isfinite(benchmark) or benchmark <= 0:
        raise AnalysisError('Intensity benchmark must be finite and positive')
    I_pts = clamp(100 * (1.5 - (eui_year / benchmark)))

    return I_pts


# Sustainability score P2: After-hours use 
# --> Does the building switch things off when closed
def after_hours_points(energy_share, time_share):
    """H = clamp(100 * (1 - SE / ST))
        ( Nothing used when closed : 100 pts )
    """
    if time_share == 0:
        return 100.0        # never closed -> nothing to judge, i.e. full pts

    H_pts = clamp(100 * (1 - (energy_share / time_share)))

    return H_pts


# Sustainability Score - Combined P1 & P2
def sustainability_score(parts, weights):
    """Weighted sum -> Score = (W1 * I) + (W2 * H)"""

    total = 0
    for name in weights:        # from config.toml, weights = {"intensity": 0.6, "after_hours": 0.4}
        total += parts[name] * weights[name]

    return round(total, 1)

# Sustainability Grade
def grade(score):
    if score >= 85:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 55:
        return "C"
    elif score >= 40:
        return "D"
    else:
        return "E"


# How much more or less than before
def change_pct(now, before):
    """+ 10.0 -> 10 % more than before; None = nothing to compare with"""

    if before == 0:
        return None

    return round((now - before) / before * 100, 1)


# Seasonal Native Forecast
# Average of same X weekday from last 4 weeks = Next X weekday
def forecast_same_hour(hourly, days=7, weeks=4):
    """Next reading at time, t = Average of last four weeks of reading at exact time, t"""

    if (isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 30
            or isinstance(weeks, bool) or not isinstance(weeks, int) or weeks <= 0):
        raise AnalysisError('Forecast needs 1–30 days and a positive integer history window')
    if (hourly.empty or not isinstance(hourly.index, pd.DatetimeIndex)
            or hourly.index.tz is None or not hourly.index.is_monotonic_increasing
            or not hourly.index.is_unique or not np.isfinite(hourly.to_numpy()).all()):
        raise AnalysisError('Forecast needs finite, ordered, timezone-aware hourly history')
    # keep only the last 4 weeks of hourly values
    last_hour = hourly.index.max()
    cutoff = last_hour - pd.Timedelta(weeks = weeks)
    recent = hourly[hourly.index > cutoff]

    # one average for every (weekday, hour) of the week: 7 x 24 = 168 averages
    weekdays = recent.index.day_of_week     # 0 = Monday ... 6 = Sunday
    hours = recent.index.hour               # 0 ... 23
    
    profile = recent.groupby([weekdays, hours]).mean()


    # Create Future Data Package
    # Future hours: start 1 hour after the last known hour
    first_future_hour = last_hour + pd.Timedelta("1h")
    future = pd.date_range(first_future_hour, periods = days * 24, freq = "h")

    # Future Values: each future hour gets the average of its (weekday, hour)
    values = []
    for ts in future:
        key = (ts.day_of_week, ts.hour)         # e.g. (0, 10) => Monday 10:00
        if key not in profile:
            raise AnalysisError('Insufficient history for the requested weekday/hour forecast')
        values.append(profile[key]) # NaN if that hour never appeared

    forecast = pd.Series(values, index = future, name = "forecast_kwh")

    return forecast.round(3)

