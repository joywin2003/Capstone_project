# Flask API

Run on `http://127.0.0.1:5001` with `python -m flask --app backend.web.app run --port 5001`.

| GET route | Output |
|---|---|
| `/` | HTML building table from configured database |
| `/api/buildings` | Array of objects with `id`, `name`, `type`, `floor_area_m2` |
| `/api/buildings/<id>/latest` | `last_reading`, `power_kw`, and `zones` |
| `/api/buildings/<id>/kpis?start=...&end=...` | `energy_kwh`, `cost_eur`, `co2_kg`, `eui_kwh_m2_yr`, `period_days`, `completeness` |
| `/api/buildings/<id>/timeseries?start=...&end=...&freq=1h` | Array of timestamped zone-energy records |

Both period parameters are mandatory. Use ISO 8601 timestamps including offsets; an unambiguous naive timestamp means Europe/Berlin. Periods include start and exclude end. Supported frequencies: `15min`, `1h`, `1D`. Energy is interval kWh, power is average kW, money is EUR, emissions are kg CO2. UTC is used in storage; latest-reading output uses Berlin-local offsets, while JSON timeseries timestamps use UTC with a `Z` suffix. Missing numeric timeseries values serialize as JSON `null`.

Example request:

```text
GET /api/buildings/1/kpis?start=2016-12-01T00:00:00Z&end=2016-12-02T00:00:00Z
```

Example seeded result:

```json
{"energy_kwh":48.0,"cost_eur":14.4,"co2_kg":18.2,"eui_kwh_m2_yr":125.1,"period_days":1.0,"completeness":1.0}
```

Invalid input returns 400, unknown buildings 404, and database failures 503, analysis failures 422, and unexpected failures 500. Error bodies have the shape `{"error":{"code":"...","message":"..."}}`. Empty valid periods return empty records / zero consumption and zero completeness, rather than inventing measurements.
