"""Stable errors: messages describe failures, never echo raw backend/model exceptions."""


class NLQueryError(Exception):
    """Base for safe, caller-visible errors."""


class ConfigurationError(NLQueryError):
    """Invalid configuration or unavailable optional dependency."""


class ConnectorError(NLQueryError):
    """Backend connection failure."""


class SchemaDiscoveryError(ConnectorError):
    """Schema discovery failed or exceeded its budget."""


class IntentError(NLQueryError):
    """Interpretation failed validation."""


class AmbiguityError(IntentError):
    """Interpretation requires clarification."""

    def __init__(self, ambiguities: object) -> None:
        super().__init__("Clarification required; inspect ambiguities.")
        self.ambiguities = ambiguities


class PlanningError(NLQueryError):
    """Invalid semantic plan."""


class CompilationError(NLQueryError):
    """Cannot render a valid plan."""


class ValidationError(NLQueryError):
    """Invalid schema reference or compiled artifact."""


class PolicyViolation(ValidationError):
    """Operation violates configured policy."""


class ExecutionError(NLQueryError):
    """Backend execution failed."""


class UnsupportedCapabilityError(PlanningError):
    """Backend cannot preserve requested semantics."""
