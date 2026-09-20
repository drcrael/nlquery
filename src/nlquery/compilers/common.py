"""Shared proposal construction; no backend syntax lives here."""

from typing import Any

from nlquery.core.models import CompiledQuery, QueryPlan, QueryRisk


def proposal(
    backend: str, language: str, query: Any, parameters: dict[str, Any], plan: QueryPlan
) -> CompiledQuery:
    reasons = []
    if not plan.ir.predicate:
        reasons.append("No selective predicate; bounded results do not bound scanned data")
    if plan.ir.joins:
        reasons.append("Join cost depends on indexes and cardinality")
    if plan.ir.traversal:
        reasons.append("Traversal fan-out depends on graph topology")
    return CompiledQuery(
        backend=backend,
        language=language,
        query=query,
        parameters=parameters,
        plan=plan,
        explanation=" → ".join(n.operation for n in plan.nodes),
        referenced_objects=plan.ir.sources,
        risk=QueryRisk(level="medium" if reasons else "low", reasons=reasons),
        warnings=reasons,
        confidence=plan.confidence,
        provenance=plan.provenance,
    )
