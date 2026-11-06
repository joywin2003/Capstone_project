"""Run only against a disposable energy_homework_test* database."""

from contextlib import closing
import os

import pandas as pd
import pytest
from sqlalchemy.engine import make_url
from backend.errors import DatabaseAccessError

from backend.db import database
from backend.db.seed import initialize
from backend.web.app import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def mysql_url():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.fail('Set TEST_DATABASE_URL to a disposable MySQL energy_homework_test* database')
    parsed = make_url(url)
    if parsed.get_backend_name() != 'mysql' or not (parsed.database or '').startswith('energy_homework_test'):
        pytest.fail('Integration tests require MySQL and a dedicated energy_homework_test* database')
    engine = database.engine_for(url)
    database.metadata.drop_all(engine)
    initialize(url, sample=True)
    yield url
    database.metadata.drop_all(engine)


def test_mysql_persists_building_and_readings(mysql_url):
    with closing(database.engine_for(mysql_url).connect()) as con:
        assert len(database.list_buildings(con)) == 2
        readings = database.load_readings(con, 1, pd.Timestamp('2016-12-01T00:00Z'), pd.Timestamp('2016-12-02T00:00Z'))
        assert len(readings) == 96
        assert readings.value.sum() == 48
    # A new engine/connection proves data was committed, not just held in memory.
    database.engine_for(mysql_url).dispose()
    assert create_app({'DATABASE_URL': mysql_url}).test_client().get('/api/buildings').json[0]['name'] == 'Demo Home'


def test_mysql_repeated_ingestion_is_idempotent(mysql_url):
    initialize(mysql_url, sample=True)
    with closing(database.engine_for(mysql_url).connect()) as con:
        count = con.execute(database.select(database.func.count()).select_from(database.reading_table)).scalar_one()
        assert count == 192


def test_mysql_constraint_failure_rolls_back_batch(mysql_url):
    with closing(database.engine_for(mysql_url).connect()) as con:
        with pytest.raises(DatabaseAccessError):
            database.save_readings(con, 999999, pd.Series([1.0, 2.0], index=pd.date_range('2017-01-01', periods=2, freq='15min', tz='UTC')))
        assert con.execute(database.select(database.func.count()).select_from(database.reading_table)).scalar_one() == 192


def test_mysql_flask_kpi_output(mysql_url):
    client = create_app({'DATABASE_URL': mysql_url}).test_client()
    response = client.get('/api/buildings/1/kpis', query_string={
        'start': '2016-12-01T00:00:00Z', 'end': '2016-12-02T00:00:00Z'})
    assert response.status_code == 200
    assert response.json['energy_kwh'] == 48
    assert response.json['cost_eur'] == 14.4
    assert 'Demo Home' in client.get('/').text
