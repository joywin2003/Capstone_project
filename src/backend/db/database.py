"""Database access layer shared by ingestion, analysis, Flask, and Streamlit.

MySQL is the homework database. SQLite remains available for offline development
and deterministic tests. Timestamps use canonical UTC text for schema compatibility.
"""

from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sqlalchemy import (CheckConstraint, Column, Float, ForeignKey, Integer,
                        MetaData, String, Table, UniqueConstraint, create_engine,
                        event, func, select)
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend import settings

TS_FORMAT = '%Y-%m-%dT%H:%M:%SZ'
DATABASE_OVERRIDE = ContextVar('energy_database_url', default=None)
metadata = MetaData()
building_table = Table('building', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(150), nullable=False, unique=True),
    Column('type', String(30), nullable=False),
    Column('floor_area_m2', Float, nullable=False),
    CheckConstraint('floor_area_m2 > 0', name='positive_floor_area'))
zone_table = Table('zone', metadata,
    Column('id', Integer, primary_key=True),
    Column('building_id', ForeignKey('building.id'), nullable=False),
    Column('name', String(100), nullable=False),
    UniqueConstraint('building_id', 'name'))
meter_table = Table('meter', metadata,
    Column('id', Integer, primary_key=True),
    Column('zone_id', ForeignKey('zone.id'), nullable=False),
    Column('kind', String(30), nullable=False),
    Column('unit', String(30), nullable=False),
    Column('source', String(150), nullable=False, default=''),
    UniqueConstraint('zone_id', 'kind', 'source'))
reading_table = Table('reading', metadata,
    Column('meter_id', ForeignKey('meter.id'), primary_key=True),
    Column('ts_utc', String(20), primary_key=True),
    Column('value', Float, nullable=False),
    CheckConstraint('value >= 0', name='nonnegative_energy'))


def configured_url():
    return DATABASE_OVERRIDE.get() or settings.DATABASE_URL


@lru_cache(maxsize=8)
def engine_for(url):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def foreign_keys(dbapi_connection, _):
            dbapi_connection.execute('PRAGMA foreign_keys = ON')
    return engine


def connect(path=None):
    url = configured_url()
    if path is not None:
        url = 'sqlite:///:memory:' if str(path) == ':memory:' else f'sqlite:///{Path(path).resolve()}'
    return engine_for(url).connect()


def create_tables(con):
    metadata.create_all(con)
    con.commit()


def ts_text(ts):
    value = pd.Timestamp(ts)
    if pd.isna(value) or value.tzinfo is None:
        raise ValueError('Timestamp must be timezone-aware')
    return value.tz_convert('UTC').strftime(TS_FORMAT)


def _get_or_create(con, table, identity, values):
    condition = [table.c[key] == value for key, value in identity.items()]
    row_id = con.execute(select(table.c.id).where(*condition)).scalar_one_or_none()
    if row_id is None:
        row_id = con.execute(table.insert().values(**values)).inserted_primary_key[0]
    return row_id


def save_building(con, building):
    try:
        building.id = _get_or_create(con, building_table, {'name': building.name}, {
            'name': building.name, 'type': building.building_type,
            'floor_area_m2': building.floor_area_m2})
        for zone in building.zones:
            identity = {'building_id': building.id, 'name': zone.name}
            zone.id = _get_or_create(con, zone_table, identity, identity)
            for meter in zone.meters:
                identity = {'zone_id': zone.id, 'kind': meter.kind, 'source': meter.source}
                meter.id = _get_or_create(con, meter_table, identity, {**identity, 'unit': meter.unit})
        con.commit()
        return building.id
    except Exception:
        con.rollback()
        raise


def save_readings(con, meter_id, values):
    if values.empty:
        return 0
    if values.index.tz is None or not values.index.is_unique:
        raise ValueError('Reading timestamps must be unique and timezone-aware')
    import numpy as np
    if not np.isfinite(values.to_numpy(dtype=float)).all() or (values < 0).any():
        raise ValueError('Readings must be finite and nonnegative')
    rows = [{'meter_id': meter_id, 'ts_utc': ts_text(ts), 'value': float(value)}
            for ts, value in values.items()]
    count = select(func.count()).select_from(reading_table).where(reading_table.c.meter_id == meter_id)
    try:
        before = con.execute(count).scalar_one()
        for offset in range(0, len(rows), 1000):
            batch = rows[offset:offset + 1000]
            if con.dialect.name == 'mysql':
                statement = mysql_insert(reading_table).values(batch)
                statement = statement.on_duplicate_key_update(value=reading_table.c.value)
            else:
                statement = sqlite_insert(reading_table).values(batch).on_conflict_do_nothing(
                    index_elements=['meter_id', 'ts_utc'])
            con.execute(statement)
        added = con.execute(count).scalar_one() - before
        con.commit()
        return added
    except Exception:
        con.rollback()
        raise


def list_buildings(con):
    return [dict(row) for row in con.execute(select(building_table).order_by(building_table.c.id)).mappings()]


def load_building(con, building_id):
    row = con.execute(select(building_table).where(building_table.c.id == building_id)).mappings().first()
    return dict(row) if row else None


def _reading_join():
    return reading_table.join(meter_table).join(zone_table)


def load_readings(con, building_id, start, end, kind='electricity'):
    statement = select(reading_table.c.ts_utc.label('ts'), zone_table.c.name.label('zone'),
                       reading_table.c.value).select_from(_reading_join()).where(
        zone_table.c.building_id == building_id, meter_table.c.kind == kind,
        reading_table.c.ts_utc >= ts_text(start), reading_table.c.ts_utc < ts_text(end)
    ).order_by(reading_table.c.ts_utc)
    df = pd.DataFrame(con.execute(statement).mappings().all(), columns=['ts', 'zone', 'value'])
    df['ts'] = pd.to_datetime(df['ts'], utc=True)
    return df


def latest_ts(con, building_id=None):
    statement = select(func.max(reading_table.c.ts_utc)).select_from(_reading_join()).where(
        meter_table.c.kind == 'electricity')
    if building_id is not None:
        statement = statement.where(zone_table.c.building_id == building_id)
    value = con.execute(statement).scalar_one()
    return pd.Timestamp(value) if value else None
