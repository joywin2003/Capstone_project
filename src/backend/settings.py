"""settings.py - loads config.toml once and knows where the database file is"""

import os
import tomllib

from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).parents[2]        # src/backend/settings.py -> up 2 folders = repo root folder

load_dotenv(ROOT / ".env")

with open(ROOT / "config.toml", "rb") as f:     # tomllib wants the file opened as bytes (rb = read byte)
    CONFIG = tomllib.load(f)

DB_PATH = os.environ.get("DB_PATH", str(ROOT / "energy.db"))    # database path
LOCAL_TZ = CONFIG["site"]["timezone"]   # shortcut for time zone (used a lot)

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")
