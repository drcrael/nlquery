"""Provider-independent intent metrics. Mock replays never imply model accuracy."""

from typing import Any

from nlquery import NLQuery
from nlquery.core.models import QueryIntent
from nlquery.core.planner import all_filters
from nlquery.exceptions import NLQueryError


def score_intent(expected: QueryIntent, actual: QueryIntent) -> dict[str, bool]:
    def fields(q: QueryIntent) -> list[str]:
        return sorted(
            [p.field for p in q.projections]
            + q.dimensions
            + [m.field for m in q.metrics]
            + [f.field for f in all_filters(q)]
        )

    def filters(q: QueryIntent) -> Any:
        return [
            f.model_dump() for f in q.filters
        ], q.predicate.model_dump() if q.predicate else None

    return {
        "source_accuracy": sorted(expected.sources) == sorted(actual.sources),
        "field_accuracy": fields(expected) == fields(actual),
        "filter_accuracy": filters(expected) == filters(actual),
        "aggregation_accuracy": expected.metrics == actual.metrics
        and expected.dimensions == actual.dimensions,
        "relationship_accuracy": expected.joins == actual.joins
        and expected.traversal == actual.traversal,
        "time_accuracy": [f for f in all_filters(expected) if f.operator == "relative_time"]
        == [f for f in all_filters(actual) if f.operator == "relative_time"]
        and expected.window == actual.window,
        "ambiguity_detection": bool(expected.ambiguities) == bool(actual.ambiguities),
        "exact_intent_match": expected == actual,
    }


def evaluate(client: NLQuery, cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for case in cases:
        try:
            expected = QueryIntent.model_validate(case["intent"])
            actual = client.interpret(case["question"])
            rows.append({"id": case["id"], "metrics": score_intent(expected, actual)})
        except (NLQueryError, ValueError):
            rows.append({"id": case["id"], "error": "interpretation_failed"})
    return {
        "cases": rows,
        "count": len(rows),
        "interpretation_failures": sum("error" in r for r in rows),
    }
