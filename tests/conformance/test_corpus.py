import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nlquery import NLQuery, QueryIntent
from nlquery.cli.main import offline
from nlquery.core.models import SchemaModel
from nlquery.evaluation import score_intent
from nlquery.exceptions import NLQueryError
from nlquery.llm.mock import MockProvider

ROOT = Path(__file__).parents[1] / "golden"
CASES = json.loads((ROOT / "cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_golden_pipeline(case):
    schema = SchemaModel.model_validate_json((ROOT / "schema.json").read_text()).model_copy(
        update={"backend": case["backend"]}
    )
    client = NLQuery(
        offline(schema),
        llm=MockProvider(case["intent"]),
        clock=lambda: datetime(2026, 7, 1, tzinfo=UTC),
    )
    if case["outcome"] == "reject":
        with pytest.raises(NLQueryError):
            client.compile(case["question"])
    else:
        q = client.compile(case["question"])
        assert client.validate(q).allowed
        expected = QueryIntent.model_validate(case["intent"])
        assert q.plan.ir.limit == expected.limit
        assert q.plan.ir.sources == expected.sources
        assert q.plan.ir.metrics == [
            m.model_copy(update={"field": "records." + m.field if m.field != "*" else "*"})
            for m in expected.metrics
        ]
        assert q.plan.ir.unresolved == []


@pytest.mark.parametrize(
    "case",
    [
        c
        for c in CASES
        if c["outcome"] == "compile" and c["backend"] == "sqlite" and c["id"] != "nl-38"
    ],
    ids=lambda c: c["id"],
)
def test_cross_backend_semantic_plan(case):
    plans = []
    for backend in ["sqlite", "postgres", "mongo", "neo4j"]:
        schema = SchemaModel.model_validate_json((ROOT / "schema.json").read_text()).model_copy(
            update={"backend": backend}
        )
        client = NLQuery(offline(schema), clock=lambda: datetime(2026, 7, 1, tzinfo=UTC))
        plans.append(client.compile(QueryIntent.model_validate(case["intent"])).plan.ir)
    assert all(plan == plans[0] for plan in plans)


def test_evaluator_detects_semantic_drift():
    expected = QueryIntent(sources=["records"], limit=10)
    actual = QueryIntent(sources=["other"], limit=100)
    score = score_intent(expected, actual)
    assert not score["source_accuracy"]
    assert not score["exact_intent_match"]
