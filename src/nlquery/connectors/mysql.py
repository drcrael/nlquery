"""MySQL 8 read-only queries with MAX_EXECUTION_TIME and explicit namespace."""

from typing import Any

from nlquery.compilers.sql import SQLCompiler
from nlquery.connectors.base import dtype, verified
from nlquery.core.models import (
    CompiledQuery,
    ConnectorCapabilities,
    DiscoveryConfig,
    FieldSchema,
    QueryPolicy,
    SchemaModel,
    SourceSchema,
)
from nlquery.exceptions import ConfigurationError, ExecutionError, SchemaDiscoveryError


class MySQLConnector:
    backend = "mysql"
    capabilities = ConnectorCapabilities(aggregation=True, calculations=True, distinct=True)

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        database: str,
        *,
        port: int = 3306,
        discovery: DiscoveryConfig | None = None,
    ) -> None:
        self._options = dict(host=host, user=user, password=password, database=database, port=port)
        self.config = discovery or DiscoveryConfig()
        self.compiler = SQLCompiler("mysql")

    def __repr__(self) -> str:
        return "MySQLConnector(credentials=<redacted>)"

    def secret_values(self) -> list[str]:
        return [str(self._options["password"])]

    def _connect(self, timeout: float = 10) -> Any:
        try:
            import pymysql
        except ImportError:
            raise ConfigurationError("Install nlquery[mysql]") from None
        return pymysql.connect(
            **self._options, connect_timeout=10, read_timeout=timeout, write_timeout=timeout
        )

    def discover(self) -> SchemaModel:
        conn = None
        try:
            conn = self._connect()
            with conn.cursor() as cur:
                cur.execute("SET SESSION MAX_EXECUTION_TIME=10000")
                cur.execute(
                    "SELECT TABLE_NAME,TABLE_TYPE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME LIMIT %s",
                    (self._options["database"], self.config.max_sources + 1),
                )
                tables = cur.fetchall()
                if len(tables) > self.config.max_sources:
                    raise SchemaDiscoveryError("Source budget exceeded")
                sources = []
                for name, kind in tables:
                    cur.execute(
                        "SELECT COLUMN_NAME,DATA_TYPE,IS_NULLABLE,COLUMN_KEY FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION LIMIT %s",
                        (self._options["database"], name, self.config.max_fields + 1),
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
                                primary_key=r[3] == "PRI",
                                indexed=bool(r[3]),
                            )
                        )
                        for r in rows
                    ]
                    sources.append(
                        SourceSchema(
                            name=name, kind="view" if kind == "VIEW" else "table", fields=fields
                        )
                    )
                return SchemaModel(backend=self.backend, sources=sources)
        except (ConfigurationError, SchemaDiscoveryError):
            raise
        except Exception:
            raise SchemaDiscoveryError("MySQL discovery failed") from None
        finally:
            if conn is not None:
                conn.close()

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        canonical = verified(self, query, policy)
        conn = None
        try:
            conn = self._connect(policy.max_execution_seconds)
            with conn.cursor() as cur:
                cur.execute(
                    "SET SESSION MAX_EXECUTION_TIME=%s",
                    (max(1, int(policy.max_execution_seconds * 1000)),),
                )
                cur.execute("START TRANSACTION READ ONLY")
                cur.execute(canonical.query, canonical.parameters)
                names = [c[0] for c in cur.description]
                return [
                    dict(zip(names, row, strict=True))
                    for row in cur.fetchmany(canonical.plan.ir.limit)
                ]
        except ConfigurationError:
            raise
        except Exception:
            raise ExecutionError("MySQL read failed or exceeded its deadline") from None
        finally:
            if conn is not None:
                conn.rollback()
                conn.close()
