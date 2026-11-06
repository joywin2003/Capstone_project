"""Translate backend domain failures into a dashboard-specific exception."""

from backend.errors import DashboardError, EnergyPlatformError


def dashboard_action(action):
    try:
        return action()
    except EnergyPlatformError as exc:
        message = str(exc) if exc.status_code < 500 else 'Energy data is temporarily unavailable. Please try again.'
        raise DashboardError(message) from exc
