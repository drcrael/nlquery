from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as ModelError

from nlquery.core.models import (
    Ambiguity,
    ConnectorCapabilities,
    FieldSchema,
    Filter,
    Metric,
    Projection,
    QueryIntent,
    QueryPlan,
    QueryPolicy,
    SchemaModel,
    SemanticCatalog,
    SourceSchema,
)
from nlquery.core.planner import build_plan, time_interval
from nlquery.exceptions import (
    AmbiguityError,
    PolicyViolation,
    UnsupportedCapabilityError,
    ValidationError,
)


@pytest.fixture
def schema():
    return SchemaModel(
        sources=[
            SourceSchema(
                name="orders",
                fields=[
                    FieldSchema(name="amount", data_type="number"),
                    FieldSchema(name="created", data_type="datetime"),
                ],
            )
        ]
    )


def plan(intent, schema, **kwargs):
    return build_plan(
        intent,
        schema,
        ConnectorCapabilities(aggregation=True),
        QueryPolicy(**kwargs),
        SemanticCatalog(),
        datetime(2026, 7, 1, tzinfo=UTC),
    )


def test_roundtrip(schema):
    p = plan(
        QueryIntent(
            sources=["orders"], metrics=[Metric(field="amount", aggregation="sum", alias="total")]
        ),
        schema,
    )
    assert QueryPlan.model_validate_json(p.model_dump_json()) == p
    assert p.ir.metrics[0].field == "orders.amount"
    assert p.confidence.components


@pytest.mark.parametrize("value", ["last_quarter", "previous_quarter"])
def test_quarter(value):
    assert time_interval(value, datetime(2026, 1, 1, tzinfo=UTC)) == (
        "2025-10-01T00:00:00+00:00",
        "2026-01-01T00:00:00+00:00",
    )


def test_limits(schema):
    with pytest.raises(PolicyViolation):
        plan(QueryIntent(sources=["orders"], limit=1001), schema)


def test_no_unknown_fields(schema):
    with pytest.raises(ValidationError):
        plan(QueryIntent(sources=["orders"], projections=[Projection(field="bad")]), schema)


def test_ambiguity(schema):
    with pytest.raises(AmbiguityError):
        plan(
            QueryIntent(
                sources=["orders"],
                ambiguities=[Ambiguity(term="biggest", candidates=["count", "amount"])],
            ),
            schema,
        )


def test_capability(schema):
    with pytest.raises(UnsupportedCapabilityError):
        plan(QueryIntent(sources=["orders"], distinct=True), schema)


def test_no_writes():
    with pytest.raises(ModelError):
        QueryIntent(sources=["orders"], operation="delete")


def test_time_resolution(schema):
    p = plan(
        QueryIntent(
            sources=["orders"],
            filters=[Filter(field="created", operator="relative_time", value="last_quarter")],
        ),
        schema,
    )
    assert p.ir.predicate.terms[0].value == "2026-04-01T00:00:00+00:00"
