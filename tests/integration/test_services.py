"""Real services, explicit environment opt-in. Never fall back to a fake server."""

import os

import pytest

from nlquery import NLQuery, QueryIntent
from nlquery.connectors import MongoDBConnector, Neo4jConnector, RedisConnector
from nlquery.core.models import FieldSchema, Filter, Projection, SchemaModel, SourceSchema


def required(name):
    value = os.getenv(name)
    if not value:
        pytest.skip(name + " not configured")
    return value


@pytest.mark.integration
def test_real_mongo():
    uri = required("NLQUERY_TEST_MONGO")
    from datetime import UTC, datetime

    from pymongo import MongoClient

    with MongoClient(uri) as db:
        db.nlquery_test.items.delete_many({})
        db.nlquery_test.items.insert_many(
            [
                {"name": "A", "amount": 10, "created": datetime(2026, 4, 5, tzinfo=UTC)},
                {"name": "B", "amount": 20, "created": datetime(2026, 7, 1, tzinfo=UTC)},
            ]
        )
    client = NLQuery(
        MongoDBConnector(uri, "nlquery_test"), clock=lambda: datetime(2026, 7, 1, tzinfo=UTC)
    )
    q = client.compile(
        QueryIntent(
            sources=["items"],
            projections=[Projection(field="name")],
            filters=[Filter(field="created", operator="relative_time", value="last_quarter")],
        )
    )
    assert client.execute(q).rows == [{"name": "A"}]


@pytest.mark.integration
def test_real_neo4j():
    uri = required("NLQUERY_TEST_NEO4J")
    password = required("NLQUERY_TEST_NEO4J_PASSWORD")
    from neo4j import GraphDatabase

    with GraphDatabase.driver(uri, auth=("neo4j", password)) as driver:
        driver.execute_query("MATCH (n:NLQueryTestItem) DETACH DELETE n")
        driver.execute_query(
            "CREATE (:NLQueryTestItem {name:'A', amount:10}), (:NLQueryTestItem {name:'B', amount:20})"
        )
    client = NLQuery(Neo4jConnector(uri, "neo4j", password))
    q = client.compile(
        QueryIntent(
            sources=["NLQueryTestItem"],
            projections=[Projection(field="NLQueryTestItem.name", alias="name")],
            filters=[Filter(field="amount", operator=">", value=15)],
        )
    )
    assert client.execute(q).rows == [{"name": "B"}]


@pytest.mark.integration
def test_real_redis():
    uri = required("NLQUERY_TEST_REDIS")
    import redis

    with redis.Redis.from_url(uri) as db:
        db.hset("nlquery:test:hash", mapping={"name": "A"})
    schema = SchemaModel(
        backend="redis",
        sources=[
            SourceSchema(
                name="cache",
                kind="key",
                key="nlquery:test:hash",
                key_type="hash",
                fields=[FieldSchema(name="name", data_type="string")],
            )
        ],
    )
    client = NLQuery(RedisConnector(uri, schema))
    q = client.compile(QueryIntent(sources=["cache"], projections=[Projection(field="name")]))
    assert client.execute(q).rows == [{"name": "A"}]
