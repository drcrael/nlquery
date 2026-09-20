import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest

from nlquery import NLQuery, QueryIntent, QueryPolicy
from nlquery.connectors import SQLiteConnector
from nlquery.core.models import Filter, Metric, Projection, Sort
from nlquery.exceptions import PolicyViolation, ValidationError
from nlquery.llm.mock import MockProvider


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "sales.db"
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(
            "CREATE TABLE orders (customer TEXT, amount REAL, status TEXT, created TIMESTAMP); INSERT INTO orders VALUES ('A',100,'paid','2026-04-05T00:00:00+00:00'),('A',50,'paid','2026-05-05T00:00:00+00:00'),('B',300,'cancelled','2026-05-05T00:00:00+00:00'),('B',20,'paid','2026-01-05T00:00:00+00:00');"
        )
    return NLQuery(SQLiteConnector(path), clock=lambda: datetime(2026, 7, 1, tzinfo=UTC))


def test_vertical_slice(client):
    intent = QueryIntent(
        sources=["orders"],
        operation="aggregate",
        dimensions=["customer"],
        metrics=[Metric(field="amount", aggregation="sum", alias="revenue")],
        filters=[
            Filter(field="status", operator="!=", value="cancelled"),
            Filter(field="created", operator="relative_time", value="last_quarter"),
        ],
        sort=[Sort(field="revenue", direction="desc")],
        limit=10,
    )
    client.llm = MockProvider(intent)
    compiled = client.ask("Top ten customers by revenue last quarter excluding cancelled orders")
    assert client.validate(compiled).allowed
    assert "cancelled" not in compiled.query
    assert client.execute(compiled).data == [{"customer": "A", "revenue": 150.0}]


def test_tamper(client):
    compiled = client.compile(
        QueryIntent(sources=["orders"], projections=[Projection(field="customer")])
    )
    with pytest.raises(ValidationError):
        client.execute(compiled.model_copy(update={"query": "DELETE FROM orders"}))
    assert not client.validate(compiled.model_copy(update={"parameters": {"p0": 100000}})).allowed


def test_changed_policy(client):
    compiled = client.compile(QueryIntent(sources=["orders"], limit=100))
    client.policy = QueryPolicy(max_rows=2)
    with pytest.raises(PolicyViolation):
        client.execute(compiled)


@pytest.mark.parametrize("value", ["' OR 1=1 --", "x%; DROP TABLE orders;--", "_", "%", "!"])
def test_values(client, value):
    q = client.compile(
        QueryIntent(sources=["orders"], filters=[Filter(field="customer", value=value)])
    )
    assert value not in q.query
    assert client.execute(q).row_count == 0


def test_no_llm(client):
    q = client.compile(
        QueryIntent(sources=["orders"], projections=[Projection(field="customer")], distinct=True)
    )
    assert client.execute(q).row_count == 2


def test_sqlite_without_extension_loading(client, monkeypatch):
    original = sqlite3.connect

    class NoExtensions:
        def __init__(self, *args, **kwargs):
            self.connection = original(*args, **kwargs)

        def __getattr__(self, name):
            if name == "enable_load_extension":
                raise AttributeError(name)
            return getattr(self.connection, name)

    monkeypatch.setattr(sqlite3, "connect", NoExtensions)
    assert client.connector.discover().sources
    query = client.compile(QueryIntent(sources=["orders"], limit=2))
    assert client.execute(query).row_count == 2
    connection = client.connector._connect()
    try:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM orders")
    finally:
        connection.close()
