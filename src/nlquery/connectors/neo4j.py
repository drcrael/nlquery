"""Neo4j bounded schema sampling and timed read sessions."""

from itertools import islice
from typing import Any

from nlquery.compilers.cypher import CypherCompiler
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
    checked_name,
)
from nlquery.exceptions import ConfigurationError, ExecutionError, SchemaDiscoveryError


class Neo4jConnector:
    backend = "neo4j"
    capabilities = ConnectorCapabilities(aggregation=True, graph_traversal=True, distinct=True)

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
        discovery: DiscoveryConfig | None = None,
    ) -> None:
        self._uri, self._user, self._password = uri, username, password
        self.database = database
        self.config = discovery or DiscoveryConfig()
        self.compiler = CypherCompiler()

    def __repr__(self) -> str:
        return "Neo4jConnector(credentials=<redacted>)"

    def secret_values(self) -> list[str]:
        return [self._password]

    def _driver(self) -> Any:
        try:
            from neo4j import GraphDatabase
        except ImportError:
            raise ConfigurationError("Install nlquery[neo4j]") from None
        return GraphDatabase.driver(
            self._uri, auth=(self._user, self._password), connection_timeout=10
        )

    def discover(self) -> SchemaModel:
        try:
            from neo4j import Query

            with (
                self._driver() as driver,
                driver.session(database=self.database, default_access_mode="READ") as session,
            ):
                labels = [
                    r["label"]
                    for r in session.run(
                        Query("CALL db.labels() YIELD label RETURN label LIMIT $limit", timeout=10),
                        limit=self.config.max_sources + 1,
                    )
                ]
                if len(labels) > self.config.max_sources:
                    raise SchemaDiscoveryError("Label budget exceeded")
                sources = []
                for label in labels:
                    checked_name(label)
                    records = session.run(
                        Query(
                            f"MATCH (n:`{label}`) RETURN properties(n) AS p LIMIT $limit",
                            timeout=10,
                        ),
                        limit=self.config.sample_size,
                    )
                    found: dict[str, str] = {}
                    for r in records:
                        for key, value in r["p"].items():
                            found[key] = dtype(type(value).__name__)
                            if len(found) > self.config.max_fields:
                                raise SchemaDiscoveryError("Property budget exceeded")
                    fields = [
                        FieldSchema.model_validate({"name": k, "data_type": v})
                        for k, v in sorted(found.items())
                    ]
                    sources.append(
                        SourceSchema(
                            name=label, kind="node", fields=fields, metadata={"sampled": True}
                        )
                    )
                edges = session.run(
                    Query(
                        "MATCH (a)-[r]->(b) RETURN labels(a) AS a, type(r) AS r, labels(b) AS b LIMIT $limit",
                        timeout=10,
                    ),
                    limit=self.config.sample_size,
                )
                found_edges: dict[str, Relationship] = {}
                for row in edges:
                    for a in row["a"]:
                        for b in row["b"]:
                            if a in labels and b in labels:
                                edge = Relationship(name=row["r"], source=a, target=b)
                                if row["r"] in found_edges and found_edges[row["r"]] != edge:
                                    raise SchemaDiscoveryError(
                                        "Polymorphic relationships require an explicit schema"
                                    )
                                found_edges[row["r"]] = edge
                return SchemaModel(
                    backend=self.backend, sources=sources, relationships=list(found_edges.values())
                )
        except (ConfigurationError, SchemaDiscoveryError):
            raise
        except Exception:
            raise SchemaDiscoveryError("Neo4j metadata discovery failed") from None

    def execute(self, query: CompiledQuery, policy: QueryPolicy) -> list[dict[str, Any]]:
        canonical = verified(self, query, policy)
        try:
            from neo4j import Query

            with (
                self._driver() as driver,
                driver.session(database=self.database, default_access_mode="READ") as session,
            ):
                result = session.run(
                    Query(canonical.query, timeout=policy.max_execution_seconds),
                    canonical.parameters,
                )
                return [r.data() for r in islice(result, canonical.plan.ir.limit)]
        except ConfigurationError:
            raise
        except Exception:
            raise ExecutionError("Neo4j read failed or exceeded its deadline") from None
