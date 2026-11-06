import numpy as np
import pandas as pd
import pytest

from backend.analysis import calc
from backend.errors import AnalysisError, ModelError
from backend.models import Building, Business, Home, PublicBuilding, make_building


def test_building_abstract_contract():
    with pytest.raises(TypeError):
        Building('Abstract', 100)


def test_building_opening_hours_are_polymorphic():
    monday_18 = pd.Timestamp('2016-12-05T18:00', tz='Europe/Berlin')
    sunday_12 = pd.Timestamp('2016-12-04T12:00', tz='Europe/Berlin')
    buildings = [Home('Home', 100), Business('Office', 100), PublicBuilding('Library', 100)]
    assert [b.is_open(monday_18) for b in buildings] == [True, True, False]
    assert [b.is_open(sunday_12) for b in buildings] == [True, False, False]


def test_building_rejects_invalid_area_and_type():
    for area in [0, -1, float('nan'), float('inf')]:
        with pytest.raises(ModelError):
            Home('Invalid', area)
    with pytest.raises(ModelError):
        make_building('unknown', 'Unknown', 100)


def test_energy_cost_and_carbon_totals():
    assert calc.total_kwh(pd.Series([0.5, 1.5, 2])) == 4
    assert calc.cost_eur(4, 0.30) == 1.2
    assert calc.co2_kg(4, 0.38) == 1.5


def test_eui_rejects_invalid_dimensions():
    for area, days in [(0, 1), (-1, 1), (100, 0), (100, -1), (np.nan, 1)]:
        with pytest.raises(AnalysisError):
            calc.eui_per_year(10, area, days)
    assert calc.eui_per_year(100, 100, 365) == 1


def test_completeness_uses_actual_elapsed_days():
    # Berlin's autumn DST day has 25 hours: 100 quarter-hour intervals.
    start = pd.Timestamp('2016-10-30', tz='Europe/Berlin')
    end = pd.Timestamp('2016-10-31', tz='Europe/Berlin')
    days = (end - start) / pd.Timedelta(days=1)
    assert calc.completeness(100, days) == 1
    assert calc.completeness(0, 0) == 0
    with pytest.raises(AnalysisError):
        calc.completeness(10, 1, interval_min=0)


def test_after_hours_and_empty_energy():
    series = pd.Series([1.0, 3.0], index=pd.date_range('2016-12-05T06:00', periods=2, freq='1h'))
    assert calc.after_hours(series, lambda ts: ts.hour >= 7) == (0.25, 0.5)
    assert calc.after_hours(series.iloc[:0], lambda ts: False) == (0, 0)


def test_score_boundaries_and_zero_comparison():
    assert [calc.grade(x) for x in [85, 70, 55, 40, 39.9]] == ['A', 'B', 'C', 'D', 'E']
    assert calc.clamp(-10) == 0
    assert calc.clamp(110) == 100
    assert calc.change_pct(10, 0) is None
    assert calc.change_pct(11, 10) == 10
    with pytest.raises(AnalysisError):
        calc.intensity_points(100, 0)


def test_forecast_uses_historical_weekday_hour_profile():
    index = pd.date_range('2016-11-01', periods=4 * 7 * 24, freq='h', tz='UTC')
    hourly = pd.Series([float(ts.hour + 1) for ts in index], index=index)
    forecast = calc.forecast_same_hour(hourly, days=2)
    assert len(forecast) == 48
    assert forecast.index[0] == index[-1] + pd.Timedelta(hours=1)
    assert list(forecast) == [float(ts.hour + 1) for ts in forecast.index]


def test_forecast_rejects_empty_or_insufficient_history():
    with pytest.raises(AnalysisError):
        calc.forecast_same_hour(pd.Series(dtype=float))
    hourly = pd.Series([1.0], index=pd.date_range('2016-12-01', periods=1, tz='UTC'))
    with pytest.raises(AnalysisError, match='Insufficient history'):
        calc.forecast_same_hour(hourly)
