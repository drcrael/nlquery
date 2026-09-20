from datetime import UTC, datetime

import pytest

from nlquery.compilers.sql import SQLCompiler
from nlquery.core.models import (
    ConnectorCapabilities,
    FieldSchema,
    Filter,
    QueryIntent,
    QueryPolicy,
    SchemaModel,
    SemanticCatalog,
    SourceSchema,
)
from nlquery.core.planner import build_plan


@pytest.mark.parametrize(
    "dialect,placeholder",
    [("sqlite", ":p0"), ("postgres", "%(p0)s"), ("mysql", "%(p0)s"), ("hana", "?"), ("sql", ":p0")],
)
def test_dialects(dialect, placeholder):
    schema = SchemaModel(
        sources=[SourceSchema(name="items", fields=[FieldSchema(name="name", data_type="string")])]
    )
    plan = build_plan(
        QueryIntent(sources=["items"], filters=[Filter(field="name", value="x' OR 1=1")]),
        schema,
        ConnectorCapabilities(),
        QueryPolicy(),
        SemanticCatalog(),
        datetime.now(UTC),
    )
    compiled = SQLCompiler(dialect).compile(plan, schema, QueryPolicy())
    assert compiled.parameters["p0"] == "x' OR 1=1"
    assert "x' OR" not in compiled.query
    assert placeholder in compiled.query
