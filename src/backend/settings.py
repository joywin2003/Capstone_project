"""Validated project configuration shared by CLI, dashboard, and Flask."""

import os
import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from backend.errors import ConfigurationError

ROOT = Path(__file__).parents[2]


def load_config(path):
    try:
        with open(path, 'rb') as handle:
            config = tomllib.load(handle)
        ZoneInfo(config['site']['timezone'])
        for section in ('data', 'prices', 'validation', 'benchmarks', 'score', 'buildings'):
            if section not in config:
                raise KeyError(section)
        return config
    except (OSError, ValueError, KeyError, TypeError, ZoneInfoNotFoundError) as exc:
        raise ConfigurationError('Cannot load energy configuration; check config.toml and its timezone/sections') from exc


load_dotenv(ROOT / '.env')
CONFIG = load_config(ROOT / 'config.toml')
DB_PATH = os.environ.get('DB_PATH', str(ROOT / 'energy.db'))
DATABASE_URL = os.environ.get('DATABASE_URL', f'sqlite:///{DB_PATH}')
LOCAL_TZ = CONFIG['site']['timezone']
