"""Subsystem exceptions with stable public codes and HTTP status semantics."""


class EnergyPlatformError(Exception):
    code = 'energy_platform_error'
    status_code = 500


class ConfigurationError(EnergyPlatformError):
    code = 'configuration_error'


class ModelError(EnergyPlatformError, ValueError):
    code = 'invalid_model'
    status_code = 400


class IngestionError(EnergyPlatformError, ValueError):
    code = 'ingestion_error'
    status_code = 400


class StreamProcessingError(EnergyPlatformError, ValueError):
    code = 'stream_processing_error'
    status_code = 400


class DatabaseAccessError(EnergyPlatformError):
    code = 'database_unavailable'
    status_code = 503


class AnalysisError(EnergyPlatformError, ValueError):
    code = 'analysis_error'
    status_code = 422


class RequestValidationError(EnergyPlatformError, ValueError):
    code = 'invalid_request'
    status_code = 400


class BuildingNotFoundError(EnergyPlatformError, ValueError):
    code = 'building_not_found'
    status_code = 404


class DashboardError(EnergyPlatformError):
    code = 'dashboard_error'


class AdvisorError(EnergyPlatformError):
    code = 'advisor_unavailable'
    status_code = 503
