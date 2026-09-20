import os

import pytest

from nlquery import NLQuery, QueryIntent
from nlquery.connectors.postgres import PostgresConnector
from nlquery.core.models import Filter, Metric, Projection


@pytest.mark.integration
def test_real_postgres():
    dsn = os.getenv("NLQUERY_TEST_POSTGRES")
    if not dsn:
        pytest.skip("NLQUERY_TEST_POSTGRES not configured")
    import psycopg

    with psycopg.connect(dsn) as db:
        db.execute("CREATE TABLE IF NOT EXISTS nlquery_test_items (name TEXT, amount INTEGER)")
        db.execute("TRUNCATE nlquery_test_items")
        db.execute("INSERT INTO nlquery_test_items VALUES ('A',10),('B',20)")
    client = NLQuery(PostgresConnector(dsn))
    q = client.compile(
        QueryIntent(
            sources=["nlquery_test_items"],
            metrics=[Metric(field="amount", aggregation="sum", alias="total")],
        )
    )
    assert client.execute(q).rows == [{"total": 30}]
    q = client.compile(
        QueryIntent(
            sources=["nlquery_test_items"],
            projections=[Projection(field="name")],
            filters=[Filter(field="name", value="' OR 1=1 --")],
        )
    )
    assert client.execute(q).rows == []
