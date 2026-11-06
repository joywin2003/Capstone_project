import pytest

from backend.analysis import api
from backend.advisor.service import EnergyAdvisor
from backend.db import database
from backend.errors import (AdvisorError, AnalysisError, DashboardError,
                            DatabaseAccessError)
from backend.web.app import create_app
from ui.errors import dashboard_action


def test_flask_buildings_response(client):
    response = client.get('/api/buildings')
    assert response.status_code == 200
    assert response.json[0]['name'] == 'Demo Home'
    assert 'Demo Home' in client.get('/').text


def test_flask_known_period_totals(client):
    response = client.get('/api/buildings/1/kpis', query_string={
        'start': '2016-12-01T00:00:00Z', 'end': '2016-12-02T00:00:00Z'})
    assert response.status_code == 200
    assert response.json['energy_kwh'] == 48
    assert response.json['cost_eur'] == 14.4
    assert response.json['completeness'] == 1


def test_flask_invalid_period_returns_400(client):
    for query in [None, {'start': 'bad', 'end': '2016-12-02'},
                  {'start': '2016-12-02', 'end': '2016-12-01'},
                  {'start': 'NaT', 'end': '2016-12-01'},
                  {'start': '2016-10-30T02:30:00', 'end': '2016-10-31'}]:
        response = client.get('/api/buildings/1/kpis', query_string=query)
        assert response.status_code == 400
        assert response.json['error']['code'] == 'invalid_request'


def test_flask_unknown_building_returns_404(client):
    response = client.get('/api/buildings/999999/latest')
    assert response.status_code == 404
    assert response.json['error']['code'] == 'building_not_found'


def test_flask_database_failure_returns_503(client, monkeypatch):
    def unavailable():
        raise DatabaseAccessError('secret password and SELECT private_table')
    monkeypatch.setattr(api, 'list_buildings', unavailable)
    response = client.get('/api/buildings')
    assert response.status_code == 503
    assert response.json['error']['code'] == 'database_unavailable'
    assert 'secret' not in response.text
    assert 'SELECT' not in response.text


def test_flask_unexpected_failure_returns_safe_500(client, monkeypatch):
    def broken():
        raise RuntimeError('internal filesystem secret')
    monkeypatch.setattr(api, 'list_buildings', broken)
    response = client.get('/api/buildings')
    assert response.status_code == 500
    assert response.json['error']['code'] == 'internal_error'
    assert 'secret' not in response.text


def test_flask_empty_period_and_invalid_frequency(client):
    period = {'start': '2020-01-01', 'end': '2020-01-02'}
    response = client.get('/api/buildings/1/timeseries', query_string=period)
    assert response.status_code == 200
    assert response.json == []
    response = client.get('/api/buildings/1/timeseries', query_string={**period, 'freq': 'invalid'})
    assert response.status_code == 400
    response = client.get('/api/buildings/1/kpis', query_string=period)
    assert response.json['energy_kwh'] == 0
    assert response.json['completeness'] == 0


def test_flask_timeseries_and_latest_have_timestamps(client):
    response = client.get('/api/buildings/1/timeseries', query_string={
        'start': '2016-12-01T00:00Z', 'end': '2016-12-01T01:00Z'})
    assert response.status_code == 200
    assert len(response.json) == 1
    assert response.json[0]['Whole building'] == 2
    assert response.json[0]['ts'].endswith('Z')
    assert client.get('/api/buildings/1/latest').json['power_kw'] == 2


def test_flask_unknown_route_and_method_remain_http_errors(client):
    assert client.get('/absent').status_code == 404
    assert client.post('/api/buildings').status_code == 405


def test_flask_database_context_does_not_leak(demo_url, tmp_path):
    from backend.db.seed import initialize
    empty_url = f'sqlite:///{tmp_path / "empty.sqlite3"}'
    initialize(empty_url)
    populated = create_app({'TESTING': True, 'DATABASE_URL': demo_url}).test_client()
    empty = create_app({'TESTING': True, 'DATABASE_URL': empty_url}).test_client()
    original = database.DATABASE_OVERRIDE.get()
    assert len(populated.get('/api/buildings').json) == 2
    assert empty.get('/api/buildings').json == []
    assert len(populated.get('/api/buildings').json) == 2
    assert database.DATABASE_OVERRIDE.get() == original


def test_forecast_service_rejects_invalid_horizon():
    for days in [0, -1, 31, True, 1.5]:
        with pytest.raises(ValueError):
            api.get_forecast(1, days=days)


def test_dashboard_wraps_subsystem_errors():
    def unavailable():
        raise DatabaseAccessError('private SQL')
    with pytest.raises(DashboardError) as error:
        dashboard_action(unavailable)
    assert isinstance(error.value.__cause__, DatabaseAccessError)
    assert 'private SQL' not in str(error.value)
    assert dashboard_action(lambda: 42) == 42


def test_advisor_not_configured_and_timeout():
    with pytest.raises(AdvisorError, match='not configured'):
        EnergyAdvisor().explain('Why is usage high?', {})
    def timeout(question, context):
        raise TimeoutError('provider details')
    with pytest.raises(AdvisorError) as error:
        EnergyAdvisor(timeout).explain('Why?', {'energy_kwh': 48})
    assert isinstance(error.value.__cause__, TimeoutError)
    assert 'provider details' not in str(error.value)
    assert EnergyAdvisor(lambda q, c: 'Review after-hours consumption.').explain('Why?', {})


def test_cli_initialization(app):
    result = app.test_cli_runner().invoke(args=['init-db', '--sample'])
    assert result.exit_code == 0
    assert 'Database initialized' in result.output
