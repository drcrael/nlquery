"""Explicit offline connector for supplied schemas and deterministic compilation."""

from typing import Any

from nlquery.core.interfaces import QueryCompiler
from nlquery.core.models import CompiledQuery, ConnectorCapabilities, QueryPolicy, SchemaModel
from nlquery.exceptions import UnsupportedCapabilityError


class StaticConnector:
    def __init__(
        self, schema: SchemaModel, compiler: QueryCompiler, capabilities: ConnectorCapabilities
    ) -> None:
        self.backend = schema.backend
        self._schema = schema
        self.compiler = compiler
        self.capabilities = capabilities

    def discover(self) -> SchemaModel:
        return self._schema.model_copy(deep=True)

    def secret_values(self) -> list[str]:
        return []

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        raise UnsupportedCapabilityError("StaticConnector is explicitly compile-only")
