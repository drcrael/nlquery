"""Driver/HTTP contract tests. These are NOT substitutes for live service tests."""

import json
from types import SimpleNamespace

import httpx
import pytest

from nlquery import NLQuery, QueryIntent, QueryPolicy
from nlquery.connectors import (
    HANAConnector,
    InfluxDBConnector,
    JiraConnector,
    MongoDBConnector,
    MySQLConnector,
    Neo4jConnector,
    PostgresConnector,
    RedisConnector,
    TimescaleDBConnector,
)
from nlquery.core.models import (
    FieldSchema,
    Filter,
    Projection,
    SchemaModel,
    SourceSchema,
)
from nlquery.exceptions import (
    ConfigurationError,
    SchemaDiscoveryError,
    UnsupportedCapabilityError,
)


class Context:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        return None

    def rollback(self):
        return None


class SQLFake(Context):
    description = [SimpleNamespace(name="name")]

    def __init__(self, dialect="postgres", fail=False):
        self.dialect = dialect
        self.calls = []
        self.query = ""
        self.fail = fail

    def cursor(self):
        return self

    def execute(self, query, params=None):
        self.calls.append((query, params))
        self.query = query
        if self.fail:
            raise RuntimeError("password=leaked")

    def fetchall(self):
        q = self.query.lower()
        if "information_schema.tables" in q:
            return [("items", "BASE TABLE")]
        if "information_schema.columns" in q:
            return (
                [("name", "text", "YES", "")]
                if self.dialect == "mysql"
                else [("name", "text", "YES")]
            )
        if "table_constraints" in q:
            return []
        if "timescaledb_information.dimensions" in q:
            return [("items", "name")]
        if "timescaledb_information.continuous_aggregates" in q:
            return [("items",)]
        if "sys.table_columns" in q:
            return [("ITEMS", "NAME", "NVARCHAR", "TRUE")]
        return []

    def fetchmany(self, limit):
        return [("A",)]


@pytest.mark.parametrize("kind", ["postgres", "timescaledb", "mysql"])
def test_sql_transport_contract(kind, monkeypatch):
    if kind == "mysql":
        connector = MySQLConnector("host", "user", "credential-value", "db")
    elif kind == "timescaledb":
        connector = TimescaleDBConnector("postgresql://user:credential-value@host/db")
    else:
        connector = PostgresConnector("postgresql://user:credential-value@host/db")
    fake = SQLFake(kind)
    if kind == "mysql":
        fake.description = [("name",)]
    monkeypatch.setattr(connector, "_connect", lambda *args: fake)
    client = NLQuery(connector)
    assert client.schema().sources[0].name == "items"
    query = client.compile(QueryIntent(sources=["items"]))
    assert client.execute(query).rows == [{"name": "A"}]
    assert any("READ ONLY" in call[0] for call in fake.calls)
    assert any("timeout" in call[0] or "MAX_EXECUTION_TIME" in call[0] for call in fake.calls)
    assert "credential-value" not in repr(connector)
    fake.fail = True
    with pytest.raises(SchemaDiscoveryError) as exc:
        connector.discover()
    assert "leaked" not in str(exc.value)


def test_postgres_config(monkeypatch):
    monkeypatch.delenv("ABSENT_DATABASE", raising=False)
    with pytest.raises(ConfigurationError):
        PostgresConnector.from_env("ABSENT_DATABASE")
    monkeypatch.setenv("ABSENT_DATABASE", "postgresql://user:credential-value@host/db")
    assert "credential-value" in PostgresConnector.from_env("ABSENT_DATABASE").secret_values()


def test_hana_catalog(monkeypatch):
    import sys

    fake = SQLFake()
    monkeypatch.setitem(
        sys.modules, "hdbcli", SimpleNamespace(dbapi=SimpleNamespace(connect=lambda **kwargs: fake))
    )
    connector = HANAConnector("host", 30015, "user", "credential-value", "APP")
    assert connector.discover().sources[0].fields[0].native_type == "NVARCHAR"
    with pytest.raises(UnsupportedCapabilityError):
        connector.execute(None, QueryPolicy())
    assert "credential-value" not in repr(connector)


class GraphFake(Context):
    def __init__(self):
        self.calls = []

    def session(self, **kwargs):
        assert kwargs["default_access_mode"] == "READ"
        return self

    def run(self, query, *args, **kwargs):
        text = str(query)
        self.calls.append(query)
        if "db.labels" in text:
            return [{"label": "Item"}]
        if "properties(n)" in text:
            return [{"p": {"name": "A", "amount": 3.0}}]
        if "type(r)" in text:
            return []
        return [SimpleNamespace(data=lambda: {"name": "A"})]


def test_graph_contract(monkeypatch):
    pytest.importorskip("neo4j")
    connector = Neo4jConnector("bolt://host", "user", "credential-value")
    fake = GraphFake()
    monkeypatch.setattr(connector, "_driver", lambda: fake)
    client = NLQuery(connector)
    assert client.schema().sources[0].kind == "node"
    query = client.compile(QueryIntent(sources=["Item"], projections=[Projection(field="name")]))
    assert client.execute(query).rows == [{"name": "A"}]
    assert all(q.timeout > 0 for q in fake.calls)
    assert "credential-value" not in repr(connector)


class MongoFake(Context):
    def __init__(self):
        self.calls = []

    def __getitem__(self, name):
        return self

    def list_collections(self, **kwargs):
        return iter([{"name": "items"}])

    def find(self, filter, **kwargs):
        assert kwargs["limit"] <= 50
        return iter([{"name": "A", "amount": 3.0, "profile": {"city": "Paris"}, "tags": ["x"]}])

    def aggregate(self, pipeline, **kwargs):
        self.calls.append((pipeline, kwargs))
        return iter([{"name": "A"}])


def test_mongo_contract(monkeypatch):
    connector = MongoDBConnector("mongodb://user:credential-value@host", "db")
    fake = MongoFake()
    monkeypatch.setattr(connector, "_client", lambda: fake)
    client = NLQuery(connector)
    assert "profile.city" in [f.name for f in client.schema().sources[0].fields]
    q = client.compile(QueryIntent(sources=["items"], projections=[Projection(field="name")]))
    assert client.execute(q).rows == [{"name": "A"}]
    assert fake.calls[0][1] == {"maxTimeMS": 30000, "allowDiskUse": False}
    assert "credential-value" not in repr(connector)


class RedisFake(Context):
    def __init__(self, kind):
        self.kind = kind
        self.calls = []

    def type(self, key):
        return "ReJSON-RL" if self.kind == "json" else self.kind

    def execute_command(self, *command):
        self.calls.append(command)
        return {
            "HMGET": ["A"],
            "SRANDMEMBER": ["A"],
            "ZRANGE": ["A", "3"],
            "XRANGE": [["1-0", ["name", "A"]]],
            "JSON.GET": '{"name":["A"]}',
            "FT.SEARCH": [1, "doc:1", ["name", "A"]],
            "FT.INFO": [],
        }[command[0]]


@pytest.mark.parametrize("kind", ["hash", "set", "zset", "stream", "json", "search"])
def test_redis_contract(kind, monkeypatch):
    schema = SchemaModel(
        backend="redis",
        sources=[
            SourceSchema(
                name="cache",
                kind="key",
                key="app:items",
                key_type=kind,
                fields=[FieldSchema(name="name")],
            )
        ],
    )
    connector = RedisConnector("redis://:credential-value@host", schema)
    fake = RedisFake(kind)
    monkeypatch.setattr(connector, "_client", lambda *args: fake)
    client = NLQuery(connector)
    q = client.compile(
        QueryIntent(
            sources=["cache"],
            projections=[Projection(field="name")] if kind in {"hash", "json"} else [],
        )
    )
    assert client.execute(q).row_count == 1
    assert not any(call[0] in {"KEYS", "SCAN", "EVAL"} for call in fake.calls)
    assert "credential-value" not in repr(connector)


def test_jira_pagination(monkeypatch):
    connector = JiraConnector("https://example.test", "user", "credential-value")
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(
                200, json={"values": [{"id": "status", "schema": {"type": "string"}}], "total": 1}
            )
        body = json.loads(request.content)
        assert body["maxResults"] <= 100
        if "nextPageToken" not in body:
            return httpx.Response(
                200, json={"issues": [{"key": "TEST-1"}], "nextPageToken": "next"}
            )
        return httpx.Response(200, json={"issues": [{"key": "TEST-2"}], "isLast": True})

    monkeypatch.setattr(
        connector,
        "_client",
        lambda *args: httpx.Client(
            base_url="https://example.test", transport=httpx.MockTransport(handler)
        ),
    )
    client = NLQuery(connector)
    q = client.compile(
        QueryIntent(sources=["issues"], filters=[Filter(field="status", value="Open")], limit=2)
    )
    result = client.execute(q)
    assert result.kind == "issues"
    assert result.rows == [{"key": "TEST-1"}, {"key": "TEST-2"}]
    assert "credential-value" not in repr(connector)


def test_influx_stream(monkeypatch):
    schema = SchemaModel(
        backend="influx",
        sources=[
            SourceSchema(
                name="cpu",
                kind="measurement",
                bucket="metrics",
                time_field="time",
                fields=[
                    FieldSchema(name="time", data_type="datetime"),
                    FieldSchema(name="usage", data_type="number"),
                ],
            )
        ],
    )
    connector = InfluxDBConnector("https://example.test", "credential-value", "org", schema)
    constructor = httpx.Client

    def handler(request):
        assert request.headers["Authorization"] == "Token credential-value"
        assert "range(" in json.loads(request.content)["query"]
        return httpx.Response(200, text=",result,table,_time,_value\n,,0,2026-06-01T00:00:00Z,3\n")

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: constructor(**kwargs, transport=httpx.MockTransport(handler)),
    )
    client = NLQuery(connector)
    q = client.compile(
        QueryIntent(
            sources=["cpu"],
            filters=[Filter(field="time", operator="relative_time", value="last_7_days")],
        )
    )
    assert client.execute(q).rows == [{"_time": "2026-06-01T00:00:00Z", "_value": "3"}]
