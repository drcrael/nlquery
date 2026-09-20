from datetime import UTC, datetime

import pytest

from nlquery import NLQuery, QueryIntent
from nlquery.compilers.cypher import CypherCompiler
from nlquery.compilers.jql import JQLCompiler
from nlquery.compilers.mongo import MongoCompiler
from nlquery.connectors.static import StaticConnector
from nlquery.core.models import (
    ConnectorCapabilities,
    FieldSchema,
    Filter,
    Metric,
    Predicate,
    Projection,
    Relationship,
    SchemaModel,
    Sort,
    SourceSchema,
    Traversal,
)
from nlquery.exceptions import PolicyViolation, UnsupportedCapabilityError


def make(backend):
    schema = SchemaModel(
        backend=backend,
        sources=[
            SourceSchema(
                name="items",
                fields=[
                    FieldSchema(name="name", data_type="string"),
                    FieldSchema(name="amount", data_type="number"),
                    FieldSchema(name="profile.city", data_type="string"),
                    FieldSchema(name="tags", data_type="array"),
                ],
            )
        ],
    )
    compiler = {"neo4j": CypherCompiler, "mongo": MongoCompiler, "jira": JQLCompiler}[backend]()
    caps = ConnectorCapabilities(
        aggregation=backend != "jira", arrays=backend == "mongo", distinct=backend != "jira"
    )
    return NLQuery(
        StaticConnector(schema, compiler, caps), clock=lambda: datetime(2026, 7, 1, tzinfo=UTC)
    )


@pytest.mark.parametrize("backend", ["neo4j", "mongo", "jira"])
@pytest.mark.parametrize(
    "operator", ["=", "!=", ">", ">=", "<", "<=", "in", "not_in", "exists", "is_null"]
)
def test_predicates(backend, operator):
    value = (
        True if operator in {"exists", "is_null"} else [3, 4] if operator in {"in", "not_in"} else 3
    )
    client = make(backend)
    q = client.compile(
        QueryIntent(
            sources=["items"], filters=[Filter(field="amount", operator=operator, value=value)]
        )
    )
    assert client.validate(q).allowed


@pytest.mark.parametrize("backend", ["neo4j", "mongo", "jira"])
def test_boolean(backend):
    client = make(backend)
    q = client.compile(
        QueryIntent(
            sources=["items"],
            predicate=Predicate(
                operator="or",
                terms=[
                    Filter(field="amount", value=1),
                    Predicate(operator="not", terms=[Filter(field="name", value="O'Reilly")]),
                ],
            ),
            sort=[Sort(field="amount", direction="desc")],
            limit=5,
        )
    )
    assert client.validate(q).allowed


def test_graph_depth():
    schema = SchemaModel(
        backend="neo4j",
        sources=[
            SourceSchema(name=n, kind="node", fields=[FieldSchema(name="name", data_type="string")])
            for n in ["Supplier", "Project"]
        ],
        relationships=[Relationship(name="SUPPLIES", source="Supplier", target="Project")],
    )
    client = NLQuery(
        StaticConnector(
            schema, CypherCompiler(), ConnectorCapabilities(graph_traversal=True, aggregation=True)
        )
    )
    intent = QueryIntent(
        sources=["Supplier", "Project"],
        operation="traverse",
        traversal=Traversal(relationship="SUPPLIES", max_depth=3),
    )
    q = client.compile(intent)
    assert "*1..3" in q.query
    assert client.validate(q).allowed
    with pytest.raises(PolicyViolation):
        client.compile(
            intent.model_copy(update={"traversal": Traversal(relationship="SUPPLIES", max_depth=6)})
        )


def test_mongo_nested_and_unwind():
    client = make("mongo")
    q = client.compile(
        QueryIntent(
            sources=["items"],
            unwind=["tags"],
            filters=[Filter(field="profile.city", value="$where")],
            projections=[Projection(field="name")],
        )
    )
    assert q.query[0] == {"$unwind": "$tags"}
    assert q.query[1] == {"$match": {"$and": [{"profile.city": {"$eq": "$where"}}]}}
    assert client.validate(q).allowed


@pytest.mark.parametrize("backend", ["neo4j", "mongo"])
def test_aggregate(backend):
    client = make(backend)
    q = client.compile(
        QueryIntent(
            sources=["items"],
            dimensions=["name"],
            metrics=[Metric(field="amount", aggregation="sum", alias="total")],
            sort=[Sort(field="total", direction="desc")],
        )
    )
    assert client.validate(q).allowed


def test_jql_injection():
    client = make("jira")
    value = 'x" OR project = "ADMIN'
    q = client.compile(QueryIntent(sources=["items"], filters=[Filter(field="name", value=value)]))
    assert '\\" OR' in q.query
    with pytest.raises(UnsupportedCapabilityError):
        client.compile(
            QueryIntent(
                sources=["items"], metrics=[Metric(field="*", aggregation="count", alias="n")]
            )
        )
