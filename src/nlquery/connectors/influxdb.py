"""InfluxDB 2 transport with curated measurement metadata and streamed CSV bounds."""

import csv
from typing import Any
from urllib.parse import urlsplit

from nlquery.compilers.influx import InfluxCompiler
from nlquery.connectors.base import verified
from nlquery.core.models import CompiledQuery, ConnectorCapabilities, QueryPolicy, SchemaModel
from nlquery.exceptions import ConfigurationError, ExecutionError


class InfluxDBConnector:
    backend = "influx"
    capabilities = ConnectorCapabilities(
        aggregation=True, time_series=True, projection=False, offsets=False
    )

    def __init__(
        self, url: str, token: str, org: str, schema: SchemaModel, *, version: int = 2
    ) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ConfigurationError("Invalid Influx endpoint")
        self._url, self._token, self._org = url.rstrip("/"), token, org
        self._schema = schema
        self.compiler = InfluxCompiler(version)

    def __repr__(self) -> str:
        return "InfluxDBConnector(credentials=<redacted>)"

    def secret_values(self) -> list[str]:
        return [self._token]

    def discover(self) -> SchemaModel:
        """Return explicit catalog; automatic bucket discovery is not yet supported."""
        return self._schema.model_copy(deep=True)

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        canonical = verified(self, query, policy)
        try:
            import httpx
        except ImportError:
            raise ConfigurationError("Install nlquery[influx]") from None
        try:
            with httpx.Client(
                timeout=policy.max_execution_seconds, follow_redirects=False
            ) as client:
                with client.stream(
                    "POST",
                    self._url + "/api/v2/query",
                    params={"org": self._org},
                    headers={"Authorization": "Token " + self._token, "Accept": "application/csv"},
                    json={
                        "query": canonical.query,
                        "type": "flux",
                        "dialect": {"annotations": [], "header": True},
                    },
                ) as response:
                    response.raise_for_status()
                    reader = csv.DictReader(
                        line for line in response.iter_lines() if line and not line.startswith("#")
                    )
                    rows = []
                    for row in reader:
                        rows.append(
                            {k: v for k, v in row.items() if k not in {"", "result", "table"}}
                        )
                        if len(rows) >= canonical.plan.ir.limit:
                            break
                    return rows
        except Exception:
            raise ExecutionError("InfluxDB query failed or exceeded its deadline") from None
