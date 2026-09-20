"""Jira Cloud metadata and enhanced JQL search with bounded pagination."""

from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from nlquery.compilers.jql import JQLCompiler
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


class JiraConnector:
    backend = "jira"
    capabilities = ConnectorCapabilities(offsets=False)

    def __init__(
        self, base_url: str, email: str, token: str, discovery: DiscoveryConfig | None = None
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            raise ConfigurationError("Jira requires HTTPS without embedded credentials")
        self._url, self._email, self._token = base_url.rstrip("/"), email, token
        self.config = discovery or DiscoveryConfig()
        self.compiler = JQLCompiler()

    def __repr__(self) -> str:
        return "JiraConnector(credentials=<redacted>)"

    def secret_values(self) -> list[str]:
        return [self._token]

    def _client(self, timeout: float = 10) -> Any:
        try:
            import httpx
        except ImportError:
            raise ConfigurationError("Install nlquery[jira]") from None
        return httpx.Client(
            base_url=self._url,
            auth=(self._email, self._token),
            timeout=timeout,
            follow_redirects=False,
        )

    def discover(self) -> SchemaModel:
        try:
            with self._client() as client:
                # Paginated field search avoids fetching issue content for inference.
                response = client.get(
                    "/rest/api/3/field/search",
                    params={"startAt": 0, "maxResults": self.config.max_fields},
                )
                response.raise_for_status()
                payload = response.json()
                rows = payload.get("values", [])
                if payload.get("total", len(rows)) > self.config.max_fields:
                    raise SchemaDiscoveryError(
                        "Jira field budget exceeded; provide a curated schema"
                    )
                fields = []
                for row in rows:
                    kind = row.get("schema", {}).get("type", "unknown")
                    kind = (
                        "datetime"
                        if kind in {"date", "datetime"}
                        else kind
                        if kind in {"string", "number", "array", "boolean"}
                        else "unknown"
                    )
                    fields.append(FieldSchema.model_validate(dict(name=row["id"], data_type=kind)))
                return SchemaModel(
                    backend=self.backend,
                    sources=[SourceSchema(name="issues", kind="issues", fields=fields)],
                )
        except (ConfigurationError, SchemaDiscoveryError):
            raise
        except Exception:
            raise SchemaDiscoveryError("Jira metadata discovery failed") from None

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        canonical = verified(self, query, policy)
        try:
            rows: list[dict[str, Any]] = []
            token: str | None = None
            seen: set[str] = set()
            deadline = monotonic() + policy.max_execution_seconds
            with self._client(policy.max_execution_seconds) as client:
                while len(rows) < canonical.plan.ir.limit:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise ExecutionError("Jira execution deadline exceeded")
                    payload: dict[str, Any] = {
                        "jql": canonical.query,
                        "maxResults": min(100, canonical.plan.ir.limit - len(rows)),
                        "fields": [
                            p.field.removeprefix("issues.") for p in canonical.plan.ir.projections
                        ]
                        or ["summary", "status", "priority"],
                    }
                    if token:
                        payload["nextPageToken"] = token
                    response = client.post(
                        "/rest/api/3/search/jql", json=payload, timeout=remaining
                    )
                    response.raise_for_status()
                    data = response.json()
                    rows.extend(data.get("issues", []))
                    token = data.get("nextPageToken")
                    if data.get("isLast", False) or not token:
                        break
                    if token in seen:
                        raise ExecutionError("Jira returned repeated pagination token")
                    seen.add(token)
            return rows[: canonical.plan.ir.limit]
        except (ConfigurationError, ExecutionError):
            raise
        except Exception:
            raise ExecutionError("Jira search failed") from None
