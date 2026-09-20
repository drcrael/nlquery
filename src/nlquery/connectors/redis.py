"""Capability detection for explicit keys, with no keyspace enumeration."""

from typing import Any
from urllib.parse import unquote, urlsplit

from nlquery.compilers.redis import RedisCompiler
from nlquery.connectors.base import verified
from nlquery.core.models import (
    CompiledQuery,
    ConnectorCapabilities,
    DiscoveryConfig,
    QueryPolicy,
    SchemaModel,
)
from nlquery.exceptions import ConfigurationError, ExecutionError, SchemaDiscoveryError


class RedisConnector:
    backend = "redis"
    capabilities = ConnectorCapabilities(sorting=False)

    def __init__(
        self, url: str, schema: SchemaModel, discovery: DiscoveryConfig | None = None
    ) -> None:
        self._url = url
        self._schema = schema
        self.config = discovery or DiscoveryConfig()
        self.compiler = RedisCompiler()

    def __repr__(self) -> str:
        return "RedisConnector(credentials=<redacted>)"

    def secret_values(self) -> list[str]:
        return [self._url, unquote(urlsplit(self._url).password or "")]

    def _client(self, timeout: float = 10) -> Any:
        try:
            import redis
        except ImportError:
            raise ConfigurationError("Install nlquery[redis]") from None
        return redis.Redis.from_url(
            self._url,
            socket_timeout=timeout,
            socket_connect_timeout=min(timeout, 10),
            decode_responses=True,
        )

    def discover(self) -> SchemaModel:
        if len(self._schema.sources) > self.config.max_sources:
            raise SchemaDiscoveryError("Key budget exceeded")
        try:
            with self._client() as client:
                for s in self._schema.sources:
                    if not s.key or len(s.fields) > self.config.max_fields:
                        raise SchemaDiscoveryError("Explicit key and bounded schema required")
                    if s.key_type == "search":
                        client.execute_command("FT.INFO", s.key)
                    else:
                        actual = client.type(s.key)
                        expected = "ReJSON-RL" if s.key_type == "json" else s.key_type
                        if actual != expected:
                            raise SchemaDiscoveryError(
                                "Configured Redis key type does not match server"
                            )
            return self._schema.model_copy(deep=True)
        except (ConfigurationError, SchemaDiscoveryError):
            raise
        except Exception:
            raise SchemaDiscoveryError("Redis capability discovery failed") from None

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        canonical = verified(self, query, policy)
        try:
            with self._client(policy.max_execution_seconds) as client:
                result = client.execute_command(*canonical.query)
            cmd = canonical.query[0]
            if cmd == "HMGET":
                return [dict(zip(canonical.query[2:], result, strict=True))]
            if cmd == "ZRANGE":
                return [
                    {"member": result[i], "score": float(result[i + 1])}
                    for i in range(0, len(result), 2)
                ]
            if cmd == "XRANGE":
                return [
                    {"id": row[0], "fields": dict(zip(row[1][::2], row[1][1::2], strict=True))}
                    for row in result
                ]
            if cmd == "SRANDMEMBER":
                return [{"member": v} for v in result]
            if cmd == "JSON.GET":
                import json

                return [{"document": json.loads(result)}]
            return [
                {
                    "id": result[i],
                    "fields": dict(zip(result[i + 1][::2], result[i + 1][1::2], strict=True)),
                }
                for i in range(1, len(result), 2)
            ]
        except ConfigurationError:
            raise
        except Exception:
            raise ExecutionError("Redis read failed or exceeded its deadline") from None
