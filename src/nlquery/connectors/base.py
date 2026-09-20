"""Shared revalidation used by connectors, including direct execute calls."""

from datetime import datetime

from nlquery.core.interfaces import Connector
from nlquery.core.models import (
    CompiledQuery,
    QueryIntent,
    QueryPolicy,
    SchemaModel,
    SemanticCatalog,
)
from nlquery.core.planner import build_plan
from nlquery.exceptions import ValidationError
from nlquery.guardrails.secrets import ensure_safe


def verified(
    connector: Connector,
    query: CompiledQuery,
    policy: QueryPolicy,
    schema: SchemaModel | None = None,
) -> CompiledQuery:
    """Rebuild under current schema/policy; reject edited SQL, parameters or IR."""
    query = CompiledQuery.model_validate(query.model_dump())
    ensure_safe(query.model_dump(), connector.secret_values())
    current = schema if schema is not None else connector.discover()
    plan = build_plan(
        QueryIntent.model_validate(query.plan.ir.model_dump()),
        current,
        connector.capabilities,
        policy,
        SemanticCatalog(),
        datetime.fromisoformat(query.plan.reference_time),
    )
    canonical = connector.compiler.compile(plan, current, policy)
    if (
        query.backend != connector.backend
        or query.language != canonical.language
        or query.query != canonical.query
        or query.parameters != canonical.parameters
    ):
        raise ValidationError("Compiled artifact differs from current validated semantics")
    return canonical


def dtype(native: str) -> str:
    value = native.lower()
    if value == "str":
        return "string"
    if "bool" in value:
        return "boolean"
    if any(t in value for t in ("timestamp", "date", "time")):
        return "datetime"
    if "int" in value:
        return "integer"
    if any(t in value for t in ("decimal", "numeric", "real", "double", "float")):
        return "number"
    if any(t in value for t in ("char", "text", "string")):
        return "string"
    return "unknown"
