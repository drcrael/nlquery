"""SQLite reference connector: read-only connection, authorizer and VM deadline."""

import sqlite3
from pathlib import Path
from time import monotonic
from typing import Any

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
from nlquery.exceptions import ExecutionError, SchemaDiscoveryError


class SQLiteConnector:
    backend = "sqlite"
    capabilities = ConnectorCapabilities(
        joins=True, aggregation=True, calculations=True, distinct=True, explain=True
    )

    def __init__(self, database: str | Path, discovery: DiscoveryConfig | None = None) -> None:
        self._path = Path(database).resolve()
        self.config = discovery or DiscoveryConfig()
        self.compiler = SQLCompiler("sqlite")

    def __repr__(self) -> str:
        return "SQLiteConnector(database=<redacted>)"

    def secret_values(self) -> list[str]:
        return []

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path.as_uri() + "?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only = ON")
            # Some Python builds omit extension loading entirely.
            if hasattr(conn, "enable_load_extension"):
                conn.enable_load_extension(False)
            return conn
        except Exception:
            conn.close()
            raise

    def discover(self) -> SchemaModel:
        conn = None
        try:
            conn = self._connect()
            deadline = monotonic() + 10
            conn.set_progress_handler(lambda: int(monotonic() > deadline), 1000)
            names = conn.execute(
                "SELECT name, type FROM sqlite_schema WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT ?",
                (self.config.max_sources + 1,),
            ).fetchall()
            if len(names) > self.config.max_sources:
                raise SchemaDiscoveryError("Schema exceeds configured source budget")
            sources = []
            relationships = []
            for name, kind in names:
                columns = conn.execute(
                    "SELECT * FROM pragma_table_info(?) LIMIT ?", (name, self.config.max_fields + 1)
                ).fetchall()
                if len(columns) > self.config.max_fields:
                    raise SchemaDiscoveryError("Schema exceeds configured field budget")
                fields = [
                    FieldSchema.model_validate(
                        dict(
                            name=c[1],
                            data_type=dtype(c[2]),
                            native_type=c[2],
                            nullable=not bool(c[3]),
                            primary_key=bool(c[5]),
                        )
                    )
                    for c in columns
                ]
                sources.append(SourceSchema(name=name, kind=kind, fields=fields))
                for edge in conn.execute("SELECT * FROM pragma_foreign_key_list(?)", (name,)):
                    relationships.append(
                        Relationship(
                            name=f"{name}_{edge[2]}_{edge[0]}",
                            source=name,
                            target=edge[2],
                            source_field=edge[3],
                            target_field=edge[4],
                        )
                    )
            return SchemaModel(backend=self.backend, sources=sources, relationships=relationships)
        except SchemaDiscoveryError:
            raise
        except Exception:
            raise SchemaDiscoveryError("SQLite discovery failed") from None
        finally:
            if conn is not None:
                conn.close()

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        canonical = verified(self, query, policy)
        conn = None
        try:
            conn = self._connect()
            deadline = monotonic() + policy.max_execution_seconds
            conn.set_progress_handler(lambda: int(monotonic() > deadline), 500)
            sources = set(canonical.plan.ir.sources)

            def authorize(
                action: int, arg1: str | None, arg2: str | None, db: str | None, trigger: str | None
            ) -> int:
                if action == sqlite3.SQLITE_READ:
                    return sqlite3.SQLITE_OK if arg1 in sources else sqlite3.SQLITE_DENY
                if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
                    return sqlite3.SQLITE_OK
                if action == sqlite3.SQLITE_FUNCTION and arg2 in {
                    "count",
                    "sum",
                    "avg",
                    "min",
                    "max",
                    "like",
                    "nullif",
                }:
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY

            conn.set_authorizer(authorize)
            cursor = conn.execute(canonical.query, canonical.parameters)
            columns = [c[0] for c in cursor.description or []]
            if len(columns) != len(set(columns)):
                raise ExecutionError("Duplicate result column names; use explicit aliases")
            return [
                dict(zip(columns, row, strict=True))
                for row in cursor.fetchmany(min(policy.max_rows, canonical.plan.ir.limit))
            ]
        except ExecutionError:
            raise
        except Exception:
            raise ExecutionError("SQLite execution failed or exceeded its deadline") from None
        finally:
            if conn is not None:
                conn.close()
