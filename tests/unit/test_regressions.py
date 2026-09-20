import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from nlquery import NLQuery, QueryIntent
from nlquery.cli.main import main, offline
from nlquery.config import load_catalog
from nlquery.core.models import (
    FieldSchema,
    Filter,
    Metric,
    Projection,
    SchemaModel,
    SemanticCatalog,
    SemanticConcept,
    SourceSchema,
)
from nlquery.evaluation import evaluate
from nlquery.exceptions import ConfigurationError, IntentError, UnsupportedCapabilityError
from nlquery.llm.mock import MockProvider
from nlquery.plugins import load_connector


def client():
    schema = SchemaModel(
        sources=[
            SourceSchema(
                name="items",
                fields=[
                    FieldSchema(name="name", data_type="string"),
                    FieldSchema(name="amount", data_type="number"),
                ],
            )
        ]
    )
    return NLQuery(offline(schema))


def test_separate_stages_keep_provenance():
    c = client()
    c.catalog = SemanticCatalog(concepts={"revenue": SemanticConcept(candidates=["items.amount"])})
    plan = c.plan(
        QueryIntent(
            sources=["items"], metrics=[Metric(field="revenue", aggregation="sum", alias="total")]
        )
    )
    q = c.compile(plan)
    assert any(p.subject == "revenue" and p.evidence == "semantic_catalog" for p in q.provenance)


def test_semantic_condition_applied():
    c = client()
    c.catalog = SemanticCatalog(
        concepts={
            "valuable": SemanticConcept(
                candidates=["items.name"], condition=Filter(field="amount", operator=">", value=100)
            )
        }
    )
    q = c.compile(QueryIntent(sources=["items"], projections=[Projection(field="valuable")]))
    assert q.parameters["p0"] == 100
    assert c.validate(q).allowed


def test_compile_flag_never_executes(capsys):
    assert main(["compile", "--execute"]) == 2
    assert "failed" in capsys.readouterr().err


def test_plugin(monkeypatch):
    import nlquery.plugins as plugins

    fake = SimpleNamespace(load=lambda: lambda **kwargs: kwargs)
    monkeypatch.setattr(plugins, "entry_points", lambda **kwargs: [fake])
    assert load_connector("test", setting=1) == {"setting": 1}
    monkeypatch.setattr(plugins, "entry_points", lambda **kwargs: [])
    with pytest.raises(ConfigurationError):
        load_connector("missing")


def test_evaluation_reports_failure():
    c = client()
    c.llm = MockProvider({"sources": ["items"]})
    report = evaluate(
        c,
        [
            {"id": "a", "question": "Show items", "intent": {"sources": ["items"]}},
            {"id": "b", "question": "", "intent": {"sources": ["items"]}},
        ],
    )
    assert report["interpretation_failures"] == 1
    assert report["cases"][0]["metrics"]["exact_intent_match"]


def test_static_execution_fails():
    c = client()
    with pytest.raises(UnsupportedCapabilityError):
        c.execute(c.compile(QueryIntent(sources=["items"])))


def test_bad_question_and_missing_provider():
    c = client()
    with pytest.raises(IntentError):
        c.interpret("")
    with pytest.raises(ConfigurationError):
        c.interpret("Show items")


def test_context_budget():
    c = client()
    c.llm = MockProvider({"sources": ["items"]})
    c.catalog = SemanticCatalog(
        concepts={"revenue": SemanticConcept(candidates=["items.amount"], description="x" * 60000)}
    )
    with pytest.raises(IntentError):
        c.interpret("Show items")


def test_yaml_catalog(tmp_path):
    pytest.importorskip("yaml")
    path = tmp_path / "catalog.yaml"
    path.write_text("concepts:\n  revenue:\n    candidates: [items.amount]\n")
    assert load_catalog(path).concepts["revenue"].candidates == ["items.amount"]
    path.write_text("!!python/object/apply:os.system [echo unsafe]")
    with pytest.raises(ConfigurationError):
        load_catalog(path)


@pytest.mark.parametrize("backend", ["mongo", "neo4j"])
def test_array_membership_is_not_substring(backend):
    schema = SchemaModel(
        backend=backend,
        sources=[SourceSchema(name="items", fields=[FieldSchema(name="tags", data_type="array")])],
    )
    c = NLQuery(offline(schema))
    q = c.compile(
        QueryIntent(
            sources=["items"], filters=[Filter(field="tags", operator="contains", value="red")]
        )
    )
    if backend == "mongo":
        assert "$regex" not in json.dumps(q.query)
    else:
        assert " IN " in q.query and "CONTAINS" not in q.query


def test_jql_dates_and_custom_fields():
    schema = SchemaModel(
        backend="jira",
        sources=[
            SourceSchema(
                name="issues",
                fields=[
                    FieldSchema(name="updated", data_type="datetime"),
                    FieldSchema(name="customfield_123", data_type="string"),
                ],
            )
        ],
    )
    c = NLQuery(offline(schema), clock=lambda: datetime(2026, 7, 1, 12, 30, 59, tzinfo=UTC))
    q = c.compile(
        QueryIntent(
            sources=["issues"],
            filters=[
                Filter(field="updated", operator="relative_time", value="last_14_days"),
                Filter(field="customfield_123", value="Open"),
            ],
        )
    )
    assert '"2026-06-17 12:30"' in q.query
    assert 'cf[123] = "Open"' in q.query
    assert c.validate(q).allowed
