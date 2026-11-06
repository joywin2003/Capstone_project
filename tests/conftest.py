"""Small isolated databases; no network or API credentials in the default suite."""

import pytest

from backend.db import database
from backend.db.seed import initialize
from backend.web.app import create_app


@pytest.fixture
def demo_url(tmp_path):
    url = f'sqlite:///{tmp_path / "energy.sqlite3"}'
    initialize(url, sample=True)
    yield url
    database.engine_for(url).dispose()


@pytest.fixture
def app(demo_url):
    return create_app({'TESTING': True, 'DATABASE_URL': demo_url})


@pytest.fixture
def client(app):
    return app.test_client()
