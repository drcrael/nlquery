"""SAP HANA dialect and catalog discovery; execution remains explicitly experimental."""

from typing import Any

from nlquery.compilers.sql import SQLCompiler
from nlquery.connectors.base import dtype
from nlquery.core.models import (
    CompiledQuery,
    ConnectorCapabilities,
    DiscoveryConfig,
    FieldSchema,
    QueryPolicy,
    SchemaModel,
    SourceSchema,
)
from nlquery.exceptions import ConfigurationError, SchemaDiscoveryError, UnsupportedCapabilityError


class HANAConnector:
    backend = "hana"
    capabilities = ConnectorCapabilities(aggregation=True, calculations=True, distinct=True)

    def __init__(
        self,
        address: str,
        port: int,
        user: str,
        password: str,
        namespace: str,
        discovery: DiscoveryConfig | None = None,
    ) -> None:
        self._options = dict(address=address, port=port, user=user, password=password)
        self.namespace = namespace
        self.config = discovery or DiscoveryConfig()
        self.compiler = SQLCompiler("hana")

    def __repr__(self) -> str:
        return "HANAConnector(credentials=<redacted>)"

    def secret_values(self) -> list[str]:
        return [str(self._options["password"])]

    def discover(self) -> SchemaModel:
        conn = None
        try:
            from hdbcli import dbapi
        except ImportError:
            raise ConfigurationError("Install nlquery[hana]") from None
        try:
            conn = dbapi.connect(**self._options, connectTimeout=10000)
            cur = conn.cursor()
            cur.execute(
                "SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE_NAME,IS_NULLABLE FROM SYS.TABLE_COLUMNS WHERE SCHEMA_NAME=? ORDER BY TABLE_NAME,POSITION LIMIT ?",
                (self.namespace, self.config.max_sources * self.config.max_fields + 1),
            )
            rows = cur.fetchall()
            sources: dict[str, list[FieldSchema]] = {}
            for table, name, kind, nullable in rows:
                sources.setdefault(table, []).append(
                    FieldSchema.model_validate(
                        dict(
                            name=name,
                            data_type=dtype(kind),
                            native_type=kind,
                            nullable=nullable == "TRUE",
                        )
                    )
                )
                if (
                    len(sources) > self.config.max_sources
                    or len(sources[table]) > self.config.max_fields
                ):
                    raise SchemaDiscoveryError("HANA metadata budget exceeded")
            return SchemaModel(
                backend=self.backend,
                sources=[
                    SourceSchema(name=n, namespace=self.namespace, fields=f)
                    for n, f in sources.items()
                ],
            )
        except SchemaDiscoveryError:
            raise
        except Exception:
            raise SchemaDiscoveryError("HANA catalog discovery failed") from None
        finally:
            if conn is not None:
                conn.close()

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        raise UnsupportedCapabilityError(
            "HANA execution is not enabled until native timeout and read-only enforcement are integration-qualified"
        )
