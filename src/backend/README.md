# Database & Analysis (src/backend)
 
Original subsystem owner: Ourvish Lofur. Homework integration: Joywin Bennis. @team uses this section ONLY through `backend.analysis.api`.
 
## Quick start
 
Install the project first with `python -m pip install -e .`. Set `DATABASE_URL` for MySQL as described in the root README, or omit it to use local SQLite. The sample Flask initialization works without downloading OPSD.

1. Download the OPSD file (60 MB, not in Git) into `data/raw/`:
   https://data.open-power-system-data.org/household_data/2020-04-15/household_data_15min_singleindex.csv
2. Build the database (about 1 second, safe to repeat):
   `python -m backend.ingestion.opsd`
3. Optional, "live" data: `python -m backend.ingestion.replay` (Ctrl+C to stop)
4. Try the API: `python -c "from backend.analysis import api; print(api.get_kpis(4, '2016-11-01', '2016-12-01'))"`

 
## The Core Functions (backend/analysis/api.py)
 
| Function | Returns |
|---|---|
| `list_buildings()` | list of dicts: id, name, type, floor_area_m2 |
| `get_latest(building_id)` | dict: last_reading, power_kw, zones |
| `get_kpis(building_id, start, end)` | dict: energy_kwh, cost_eur, co2_kg, eui_kwh_m2_yr, period_days, completeness |
| `get_timeseries(building_id, start, end, freq="1h")` | DataFrame, one column per zone, kWh |
| `get_savings(building_id, start, end)` | dict: energy_kwh, previous_kwh, saved_kwh, saved_eur, saved_co2_kg, change_pct |
| `get_score(building_id, start, end)` | dict: score (0-100), grade (A-E), intensity_points, after_hours_points, ... |
| `get_forecast(building_id, days=7)` | DataFrame, forecast_kwh per hour |
 
Dates without a time zone mean Berlin time; `end` is excluded. Invalid requests raise `RequestValidationError`; missing buildings raise `BuildingNotFoundError`. Both retain `ValueError` compatibility. Other subsystem failures use the hierarchy in `backend.errors`.
 
## Files
 
- `settings.py` reads `config.toml` (all assumptions: prices, CO2 factor, benchmarks, buildings)
- `models.py` Building (abstract) -> Home, Business, PublicBuilding; Zone; Meter -> EnergyMeter
- `db/database.py` SQLAlchemy tables building, zone, meter, reading (MySQL or offline SQLite); the only file with SQL
- `ingestion/opsd.py` meter totals -> 15-min kWh, validation, saves to the database
- `ingestion/replay.py` feeds December 2016 in one reading at a time ("real-time")
- `analysis/calc.py` pure formulas; `analysis/api.py` the service layer
 
## For Docker
 
The container needs `config.toml`, the CSV in `data/raw/` (or a ready `energy.db`),
and `python -m backend.ingestion.opsd` once before the dashboard starts.
`DATABASE_URL` selects MySQL or offline SQLite; `DB_PATH` remains the fallback SQLite file path. See the root README for the MySQL Compose service.
 
## Known limits (v1)
 
Floor areas, benchmarks and the electricity price are placeholders (see `config.toml`).
One zone and one electricity meter per building; the classes and tables already support more.
Savings compare with the previous period of the same length, not weather-corrected.


## Verification (manual, v1)

- Import run twice: 169,378 readings, 0 rejected; second run adds 0 (idempotent).
- Time zones: October 2016 = 31.04 days (clock change handled).
- Business 1, November 2016: 20,799.62 kWh, 6,239.89 EUR, 7,903.9 kg CO2;
  -7.0 % vs October; score 35.8 (E) = 0.6 x 48.8 + 0.4 x 16.2.
- Live replay: `get_latest` moves into December; Ctrl+C stops cleanly.
- Bad input (unknown building id, start after end) raises `ValueError`.
- Automated streaming tests and MySQL integration checks are in `tests/`; see `docs/TESTING.md` for current verification.
