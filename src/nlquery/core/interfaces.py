"""Structural extension contracts: third-party implementations need no inheritance."""

from typing import Any, Protocol

from nlquery.core.models import (
    CompiledQuery,
    ConnectorCapabilities,
    QueryPlan,
    QueryPolicy,
    SchemaModel,
)


class QueryCompiler(Protocol):
    def compile(self, plan: QueryPlan, schema: SchemaModel, policy: QueryPolicy) -> CompiledQuery:
        """Render validated semantics without executing or consulting a model."""
        ...


class SchemaDiscoverer(Protocol):
    def discover(self) -> SchemaModel:
        """Return bounded metadata without credentials or sample values."""
        ...


class Connector(SchemaDiscoverer, Protocol):
    backend: str
    capabilities: ConnectorCapabilities

    @property
    def compiler(self) -> QueryCompiler: ...

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        """Execute a freshly validated read with native time and result bounds."""
        ...

    def secret_values(self) -> list[str]:
        """Known sensitive values to keep out of public artifacts."""
        ...
