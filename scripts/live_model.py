"""Actual local-model smoke evaluation and independent SQLite replay."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from nlquery import NLQuery
from nlquery.connectors import SQLiteConnector
from nlquery.core.models import Filter, Projection, QueryIntent, Sort
from nlquery.evaluation import score_intent
from nlquery.llm.providers import OllamaProvider

cases = [
    (
        "Show the names of the five items with amount greater than 10, sorted by amount descending.",
        QueryIntent(
            sources=["items"],
            projections=[Projection(field="name")],
            filters=[Filter(field="amount", operator=">", value=10)],
            sort=[Sort(field="amount", direction="desc")],
            limit=5,
        ),
    ),
    (
        "List item names where amount exceeds ten. Sort by amount from largest to smallest and return at most five.",
        QueryIntent(
            sources=["items"],
            projections=[Projection(field="name")],
            filters=[Filter(field="amount", operator=">", value=10)],
            sort=[Sort(field="amount", direction="desc")],
            limit=5,
        ),
    ),
]
report = {"provider": "ollama:qwen2.5:3b", "cases": []}
with TemporaryDirectory() as directory:
    path = Path(directory) / "items.db"
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript(
            "CREATE TABLE items(name TEXT,amount INTEGER);INSERT INTO items VALUES ('A',10),('B',20),('C',30);"
        )
    client = NLQuery(SQLiteConnector(path), llm=OllamaProvider("qwen2.5:3b", timeout=900))
    for question, expected in cases:
        row = {"question": question}
        try:
            actual = client.interpret(question)
            row["actual_intent"] = actual.model_dump(mode="json")
            row["metrics"] = score_intent(expected, actual)
            row["canonical_match"] = client.plan(expected).ir == client.plan(actual).ir
            compiled = client.compile(actual)
            result = client.execute(compiled)
            row["execution_match"] = result.rows == [{"name": "C"}, {"name": "B"}]
            row["actual_intent"] = actual.model_dump(mode="json")
            row["passed"] = row["canonical_match"] and row["execution_match"]
        except Exception as error:
            row["passed"] = False
            row["error"] = type(error).__name__
        report["cases"].append(row)
Path("live-model-report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
assert all(row["passed"] for row in report["cases"]), (
    "Live model acceptance did not pass; inspect report"
)
