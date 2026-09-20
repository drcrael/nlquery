"""Executable end-to-end acceptance scenario with an explicit mock interpreter."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from nlquery import NLQuery, QueryIntent
from nlquery.connectors import SQLiteConnector
from nlquery.core.models import Filter, Join, Metric, SemanticCatalog, SemanticConcept, Sort
from nlquery.llm.mock import MockProvider

QUESTION = "Show the ten customers with the highest revenue during the previous quarter, excluding cancelled orders."


def run() -> dict[str, object]:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "ecommerce.db"
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript("""
            CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE orders (order_id INTEGER PRIMARY KEY,customer_id INTEGER REFERENCES customers(customer_id),total_amount REAL,order_date TIMESTAMP,status TEXT);
            CREATE TABLE products (product_id INTEGER PRIMARY KEY,name TEXT,price REAL);
            CREATE TABLE order_items (order_id INTEGER REFERENCES orders(order_id),product_id INTEGER REFERENCES products(product_id),quantity INTEGER);
            INSERT INTO customers VALUES (1,'Harbor Books'),(2,'Maple Market');
            INSERT INTO orders VALUES (1,1,120,'2026-04-05T00:00:00+00:00','paid'),(2,1,80,'2026-06-30T12:00:00+00:00','paid'),(3,2,300,'2026-06-05T00:00:00+00:00','cancelled'),(4,2,50,'2026-05-10T00:00:00+00:00','paid'),(5,2,900,'2026-07-01T00:00:00+00:00','paid');
            INSERT INTO products VALUES (1,'Notebook',10),(2,'Lamp',40);
            INSERT INTO order_items VALUES (1,1,12),(2,2,2),(4,1,5);
            """)
        intent = QueryIntent(
            sources=["orders", "customers"],
            operation="aggregate",
            dimensions=["customers.name"],
            metrics=[Metric(field="revenue", aggregation="sum", alias="total_revenue")],
            joins=[Join(relationship="orders_customers_0")],
            filters=[
                Filter(field="order_date", operator="relative_time", value="previous_quarter"),
                Filter(field="status", operator="!=", value="cancelled"),
            ],
            sort=[Sort(field="total_revenue", direction="desc")],
            limit=10,
        )
        catalog = SemanticCatalog(
            concepts={
                "revenue": SemanticConcept(
                    candidates=["orders.total_amount"], aggregation="sum", units="USD"
                )
            }
        )
        client = NLQuery(
            SQLiteConnector(path),
            llm=MockProvider(intent),
            catalog=catalog,
            clock=lambda: datetime(2026, 7, 1, tzinfo=UTC),
        )
        compiled = client.compile(QUESTION)
        result = client.execute(compiled)
        assert result.rows == [
            {"name": "Harbor Books", "total_revenue": 200.0},
            {"name": "Maple Market", "total_revenue": 50.0},
        ]
        return {
            "compiled": compiled.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
            "interpreter": "deterministic mock; not a model accuracy claim",
        }


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))
