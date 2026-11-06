"""Flask factory. Run: python -m flask --app backend.web.app run --port 5001."""

import json

import click
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from backend import settings
from backend.analysis import api
from backend.db import database
from backend.errors import EnergyPlatformError, RequestValidationError


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(DATABASE_URL=settings.DATABASE_URL)
    if test_config:
        app.config.update(test_config)

    @app.before_request
    def select_database():
        request.database_token = database.DATABASE_OVERRIDE.set(app.config['DATABASE_URL'])

    @app.teardown_request
    def release_database(_error):
        token = getattr(request, 'database_token', None)
        if token is not None:
            database.DATABASE_OVERRIDE.reset(token)

    @app.get('/')
    def index():
        return render_template('index.html', buildings=api.list_buildings())

    @app.get('/api/buildings')
    def buildings():
        return jsonify(api.list_buildings())

    @app.get('/api/buildings/<int:building_id>/latest')
    def latest(building_id):
        return jsonify(api.get_latest(building_id))

    def period():
        start, end = request.args.get('start'), request.args.get('end')
        if not start or not end:
            raise RequestValidationError('Both start and end are required')
        return start, end

    @app.get('/api/buildings/<int:building_id>/kpis')
    def kpis(building_id):
        return jsonify(api.get_kpis(building_id, *period()))

    @app.get('/api/buildings/<int:building_id>/timeseries')
    def timeseries(building_id):
        frequency = request.args.get('freq', '1h')
        if frequency not in {'15min', '1h', '1D'}:
            raise RequestValidationError('freq must be 15min, 1h, or 1D')
        frame = api.get_timeseries(building_id, *period(), freq=frequency)
        # Pandas emits strict JSON null for missing values and ISO timestamps.
        return jsonify(json.loads(frame.reset_index().to_json(orient='records', date_format='iso')))

    @app.errorhandler(EnergyPlatformError)
    def domain_failure(error):
        if error.status_code >= 500:
            app.logger.error('Energy subsystem failed', exc_info=error)
        message = str(error) if error.status_code < 500 else 'Energy service is temporarily unavailable'
        return jsonify(error={'code': error.code, 'message': message}), error.status_code

    @app.errorhandler(Exception)
    def unexpected_failure(error):
        app.logger.error('Unexpected energy service failure', exc_info=error)
        return jsonify(error={'code': 'internal_error', 'message': 'An unexpected error occurred'}), 500

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error={'code': error.name.lower().replace(' ', '_'), 'message': error.description}), error.code

    @app.cli.command('init-db')
    @click.option('--sample', is_flag=True, help='Seed a small deterministic electricity dataset.')
    def init_db(sample):
        from backend.db.seed import initialize
        try:
            initialize(app.config['DATABASE_URL'], sample=sample)
        except EnergyPlatformError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo('Database initialized' + (' with sample data' if sample else ''))

    return app
