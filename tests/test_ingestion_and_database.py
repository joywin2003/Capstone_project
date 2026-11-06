from contextlib import closing

import pandas as pd
import pytest
from sqlalchemy import func, select

from backend.db import database
from backend.db.seed import initialize
from backend.errors import ConfigurationError, DatabaseAccessError, IngestionError
from backend.ingestion import opsd
from backend.settings import load_config


def test_cumulative_readings_become_intervals():
    totals = pd.Series([10., 11., 13.], index=pd.date_range('2016-12-01', periods=3, freq='15min', tz='UTC'))
    used = opsd.to_intervals(totals)
    assert list(used) == [1, 2]
    assert used.index.equals(totals.index[:2])


def test_meter_gaps_do_not_create_false_intervals():
    totals = pd.Series([10., 12., 13.], index=pd.to_datetime([
        '2016-12-01T00:00Z', '2016-12-01T00:30Z', '2016-12-01T00:45Z']))
    used = opsd.to_intervals(totals)
    assert list(used) == [1]
    assert used.index[0] == pd.Timestamp('2016-12-01T00:30Z')


def test_ingestion_rejects_invalid_readings():
    good, rejected = opsd.validate(pd.Series([-1, 0, 1, 6, float('nan'), float('inf')]), 5)
    assert list(good) == [0, 1]
    assert rejected == 4


def test_ingestion_rejects_unsorted_and_duplicate_totals():
    index = pd.to_datetime(['2016-12-01T00:15Z', '2016-12-01T00:00Z'])
    with pytest.raises(IngestionError):
        opsd.to_intervals(pd.Series([1, 2], index=index))
    with pytest.raises(IngestionError):
        opsd.to_intervals(pd.Series([1, 2], index=[index[0], index[0]]))


def test_ingestion_missing_file_and_columns(tmp_path):
    with pytest.raises(IngestionError) as error:
        opsd.read_opsd(tmp_path / 'missing.csv', ['meter'])
    assert isinstance(error.value.__cause__, OSError)
    source = tmp_path / 'bad.csv'
    source.write_text('utc_timestamp,wrong\n2016-12-01T00:00Z,1\n')
    with pytest.raises(IngestionError):
        opsd.read_opsd(source, ['meter'])


def test_configuration_missing_or_malformed(tmp_path):
    with pytest.raises(ConfigurationError):
        load_config(tmp_path / 'missing.toml')
    bad = tmp_path / 'invalid.toml'
    bad.write_text('not valid [ TOML')
    with pytest.raises(ConfigurationError):
        load_config(bad)
    bad.write_text('[site]\ntimezone="No/SuchZone"')
    with pytest.raises(ConfigurationError):
        load_config(bad)


def test_database_persists_and_deduplicates(demo_url):
    initialize(demo_url, sample=True)
    with closing(database.engine_for(demo_url).connect()) as con:
        assert con.execute(select(func.count()).select_from(database.reading_table)).scalar_one() == 192
        readings = database.load_readings(con, 1, pd.Timestamp('2016-12-01T00:00Z'), pd.Timestamp('2016-12-01T00:15Z'))
        assert list(readings.value) == [0.5]  # end-exclusive


def test_database_rejects_nonfinite_energy_and_naive_time(demo_url):
    with closing(database.engine_for(demo_url).connect()) as con:
        for value in [-1, float('nan'), float('inf')]:
            with pytest.raises(IngestionError):
                database.save_readings(con, 1, pd.Series([value], index=pd.date_range('2017-01-01', periods=1, tz='UTC')))
        with pytest.raises(IngestionError):
            database.save_readings(con, 1, pd.Series([1], index=pd.date_range('2017-01-01', periods=1)))


def test_database_failure_is_translated_with_cause(tmp_path):
    with pytest.raises(DatabaseAccessError) as error:
        database.connect(tmp_path / 'absent' / 'energy.sqlite3')
    assert error.value.__cause__ is not None
    assert str(tmp_path) not in str(error.value)


def test_database_rejects_invalid_connection_url():
    with pytest.raises(ConfigurationError):
        database.engine_for('not a database URL')


def test_opsd_import_and_replay_share_pipeline(tmp_path, monkeypatch, capsys):
    from copy import deepcopy
    from backend import settings
    from backend.ingestion import replay
    config = deepcopy(settings.CONFIG)
    config['data'].update(csv_path='totals.csv', start='2016-12-01T00:30',
                          replay_from='2016-12-01T01:00', end='2016-12-01T01:45')
    config['buildings'] = [{'name': 'Replay Home', 'type': 'home', 'floor_area_m2': 100,
                            'column': 'meter_total'}]
    pd.DataFrame({'utc_timestamp': pd.date_range('2016-11-30T23:30Z', periods=6, freq='15min'),
                  'meter_total': [0, .5, 1, 1.5, 2, 2.5]}).to_csv(tmp_path / 'totals.csv', index=False)
    monkeypatch.setattr(settings, 'ROOT', tmp_path)
    monkeypatch.setattr(settings, 'CONFIG', config)
    monkeypatch.setattr(replay.time, 'sleep', lambda seconds: None)
    token = database.DATABASE_OVERRIDE.set(f'sqlite:///{tmp_path / "replay.sqlite3"}')
    try:
        opsd.run()
        replay.run(pause=0)
        assert 'received=3 emitted=3 dropped=0' in capsys.readouterr().out
        replay.run(pause=0)  # newest interval may be resent safely after restart
        with closing(database.connect()) as con:
            readings = database.load_readings(con, 1, pd.Timestamp('2016-11-30T23:30Z'), pd.Timestamp('2016-12-01T01:00Z'))
            assert len(readings) == 5
            assert readings.value.sum() == 2.5
    finally:
        database.DATABASE_OVERRIDE.reset(token)
