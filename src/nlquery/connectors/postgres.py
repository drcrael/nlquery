"""PostgreSQL metadata and read-only transactions with statement deadlines."""

import os
from typing import Any
from urllib.parse import unquote, urlsplit

from nlquery.compilers.sql import SQLCompiler
from nlquery.connectors.base import dtype, verified
from nlquery.core.models import (
    CompiledQuery,
    ConnectorCapabilities,
    DiscoveryConfig,
    FieldSchema,
    QueryPolicy,
    Relationship,
    SchemaModel,
    SourceSchema,
)
from nlquery.exceptions import ConfigurationError, ExecutionError, SchemaDiscoveryError


class PostgresConnector:
    backend = "postgres"
    capabilities = ConnectorCapabilities(
        joins=True, aggregation=True, calculations=True, distinct=True, explain=True
    )

    def __init__(
        self,
        connection_string: str,
        *,
        namespace: str = "public",
        discovery: DiscoveryConfig | None = None,
    ) -> None:
        self._dsn = connection_string
        self.namespace = namespace
        self.config = discovery or DiscoveryConfig()
        self.compiler = SQLCompiler(self.backend)

    @classmethod
    def from_env(cls, variable: str = "DATABASE_URL") -> "PostgresConnector":
        value = os.getenv(variable)
        if not value:
            raise ConfigurationError("Required database environment variable is absent")
        return cls(value)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(connection_string=<redacted>)"

    def secret_values(self) -> list[str]:
        try:
            password = urlsplit(self._dsn).password
        except ValueError:
            password = None
        return [self._dsn] + ([unquote(password)] if password else [])

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError:
            raise ConfigurationError("Install nlquery[postgres]") from None
        return psycopg.connect(self._dsn, connect_timeout=10)

    def discover(self) -> SchemaModel:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION READ ONLY")
                    cur.execute("SELECT set_config('statement_timeout', '10000', true)")
                    cur.execute(
                        "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema=%s ORDER BY table_name LIMIT %s",
                        (self.namespace, self.config.max_sources + 1),
                    )
                    tables = cur.fetchall()
                    if len(tables) > self.config.max_sources:
                        raise SchemaDiscoveryError("Source budget exceeded")
                    sources = []
                    for name, kind in tables:
                        cur.execute(
                            "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position LIMIT %s",
                            (self.namespace, name, self.config.max_fields + 1),
                        )
                        rows = cur.fetchall()
                        if len(rows) > self.config.max_fields:
                            raise SchemaDiscoveryError("Field budget exceeded")
                        fields = [
                            FieldSchema.model_validate(
                                dict(
                                    name=r[0],
                                    native_type=r[1],
                                    data_type=dtype(r[1]),
                                    nullable=r[2] == "YES",
                                )
                            )
                            for r in rows
                        ]
                        sources.append(
                            SourceSchema(
                                name=name,
                                namespace=self.namespace,
                                kind="view" if kind == "VIEW" else "table",
                                fields=fields,
                            )
                        )
                    cur.execute(
                        """SELECT tc.constraint_name, kcu.table_name, kcu.column_name, ccu.table_name, ccu.column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.constraint_schema=kcu.constraint_schema
                        JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name=tc.constraint_name AND ccu.constraint_schema=tc.constraint_schema
                        WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema=%s LIMIT %s""",
                        (self.namespace, self.config.max_sources * self.config.max_fields + 1),
                    )
                    relationships = [
                        Relationship(
                            name=r[0],
                            source=r[1],
                            source_field=r[2],
                            target=r[3],
                            target_field=r[4],
                        )
                        for r in cur.fetchall()
                    ]
                    return SchemaModel(
                        backend=self.backend, sources=sources, relationships=relationships
                    )
        except (ConfigurationError, SchemaDiscoveryError):
            raise
        except Exception:
            raise SchemaDiscoveryError("PostgreSQL schema discovery failed") from None

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        canonical = verified(self, query, policy)
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SET TRANSACTION READ ONLY")
                    cur.execute(
                        "SELECT set_config('statement_timeout', %s, true)",
                        (str(max(1, int(policy.max_execution_seconds * 1000))),),
                    )
                    cur.execute(canonical.query, canonical.parameters)
                    columns = [c.name for c in cur.description or []]
                    if len(columns) != len(set(columns)):
                        raise ExecutionError("Duplicate output names; use aliases")
                    return [
                        dict(zip(columns, row, strict=True))
                        for row in cur.fetchmany(canonical.plan.ir.limit)
                    ]
        except (ConfigurationError, ExecutionError):
            raise
        except Exception:
            raise ExecutionError("PostgreSQL read failed or exceeded its deadline") from None
