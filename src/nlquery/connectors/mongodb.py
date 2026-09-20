"""Bounded MongoDB document inference and native aggregation deadlines."""

from datetime import datetime
from itertools import islice
from typing import Any
from urllib.parse import unquote, urlsplit

from nlquery.compilers.mongo import MongoCompiler
from nlquery.connectors.base import verified
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


class MongoDBConnector:
    backend = "mongo"
    capabilities = ConnectorCapabilities(aggregation=True, arrays=True, distinct=True)

    def __init__(self, uri: str, database: str, discovery: DiscoveryConfig | None = None) -> None:
        self._uri, self.database = uri, database
        self.config = discovery or DiscoveryConfig()
        self.compiler = MongoCompiler()

    def __repr__(self) -> str:
        return "MongoDBConnector(credentials=<redacted>)"

    def secret_values(self) -> list[str]:
        return [self._uri, unquote(urlsplit(self._uri).password or "")]

    def _client(self) -> Any:
        try:
            from pymongo import MongoClient
        except ImportError:
            raise ConfigurationError("Install nlquery[mongo]") from None
        return MongoClient(
            self._uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000, socketTimeoutMS=30000
        )

    def discover(self) -> SchemaModel:
        try:
            with self._client() as client:
                db = client[self.database]
                names = list(
                    islice(db.list_collections(nameOnly=True), self.config.max_sources + 1)
                )
                if len(names) > self.config.max_sources:
                    raise SchemaDiscoveryError("Collection budget exceeded")
                sources = []
                for item in names:
                    name = item["name"]
                    found: dict[str, str] = {}

                    def scan(
                        doc: dict[str, Any],
                        prefix: str = "",
                        depth: int = 0,
                        found: dict[str, str] = found,
                    ) -> None:
                        if depth > 8:
                            raise SchemaDiscoveryError("Document nesting exceeds discovery budget")
                        for key, v in doc.items():
                            path = prefix + key
                            kind = (
                                "boolean"
                                if isinstance(v, bool)
                                else "integer"
                                if isinstance(v, int)
                                else "number"
                                if isinstance(v, float)
                                else "datetime"
                                if isinstance(v, datetime)
                                else "string"
                                if isinstance(v, str)
                                else "array"
                                if isinstance(v, list)
                                else "object"
                                if isinstance(v, dict)
                                else "unknown"
                            )
                            if path in found and found[path] != kind:
                                found[path] = "unknown"
                            else:
                                found[path] = kind
                            if len(found) > self.config.max_fields:
                                raise SchemaDiscoveryError("Field budget exceeded")
                            if isinstance(v, dict):
                                scan(v, path + ".", depth + 1)

                    for doc in db[name].find({}, limit=self.config.sample_size, max_time_ms=10000):
                        scan(doc)
                    fields = [
                        FieldSchema.model_validate(dict(name=k, data_type=v))
                        for k, v in sorted(found.items())
                    ]
                    sources.append(
                        SourceSchema(
                            name=name,
                            kind="collection",
                            fields=fields,
                            metadata={"sampled": True, "sample_size": self.config.sample_size},
                        )
                    )
                return SchemaModel(backend=self.backend, sources=sources)
        except (ConfigurationError, SchemaDiscoveryError):
            raise
        except Exception:
            raise SchemaDiscoveryError("MongoDB discovery failed") from None

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        canonical = verified(self, query, policy)
        try:
            with self._client() as client:
                current = self.discover()
                time_fields = {
                    f.name
                    for source in current.sources
                    if source.name == canonical.plan.ir.sources[0]
                    for f in source.fields
                    if f.data_type == "datetime"
                }

                def convert(value: Any, temporal: bool = False) -> Any:
                    if isinstance(value, dict):
                        return {
                            k: convert(v, temporal or k in time_fields) for k, v in value.items()
                        }
                    if isinstance(value, list):
                        return [convert(v, temporal) for v in value]
                    if temporal and isinstance(value, str):
                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return value

                cursor = client[self.database][canonical.plan.ir.sources[0]].aggregate(
                    convert(canonical.query),
                    maxTimeMS=max(1, int(policy.max_execution_seconds * 1000)),
                    allowDiskUse=False,
                )
                return list(islice(cursor, canonical.plan.ir.limit))
        except ConfigurationError:
            raise
        except Exception:
            raise ExecutionError("MongoDB aggregation failed or exceeded its deadline") from None
