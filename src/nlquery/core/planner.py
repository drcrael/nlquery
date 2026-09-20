"""Deterministic grounding, capability validation and logical planning."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from nlquery.core.models import (
    ConfidenceAssessment,
    ConfidenceComponent,
    ConnectorCapabilities,
    Filter,
    PlanNode,
    Predicate,
    Provenance,
    QueryIntent,
    QueryIR,
    QueryPlan,
    QueryPolicy,
    SchemaModel,
    SemanticCatalog,
)
from nlquery.exceptions import (
    AmbiguityError,
    PlanningError,
    PolicyViolation,
    UnsupportedCapabilityError,
    ValidationError,
)


def time_interval(value: str, now: datetime) -> tuple[str, str]:
    """Resolve half-open UTC calendar windows using an injected clock."""
    now = now.astimezone(UTC).replace(second=0, microsecond=0)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    quarter = month.replace(month=3 * ((now.month - 1) // 3) + 1)
    if value in {"last_quarter", "previous_quarter"}:
        end = quarter
        start = (
            end.replace(year=end.year - 1, month=10)
            if end.month == 1
            else end.replace(month=end.month - 3)
        )
    elif value == "this_quarter":
        start, end = quarter, now
    elif value == "this_month":
        start, end = month, now
    elif value == "last_month":
        end = month
        start = (month - timedelta(days=1)).replace(day=1)
    elif value == "this_year":
        start, end = today.replace(month=1, day=1), now
    elif value == "last_year":
        end = today.replace(month=1, day=1)
        start = end.replace(year=end.year - 1)
    elif value == "this_week":
        start, end = today - timedelta(days=today.weekday()), now
    elif value in {"last_7_days", "last_14_days", "last_30_days"}:
        start, end = now - timedelta(days=int(value.split("_")[1])), now
    else:
        raise PlanningError("Unsupported relative time expression")
    return start.isoformat(), end.isoformat()


def all_filters(intent: QueryIntent) -> list[Filter]:
    def walk(p: Filter | Predicate) -> list[Filter]:
        return [p] if isinstance(p, Filter) else [f for t in p.terms for f in walk(t)]

    return intent.filters + (walk(intent.predicate) if intent.predicate else [])


def build_plan(
    intent: QueryIntent,
    schema: SchemaModel,
    capabilities: ConnectorCapabilities,
    policy: QueryPolicy,
    catalog: SemanticCatalog,
    now: datetime,
) -> QueryPlan:
    """Ground names without guessing; derive evidence from metadata and declared edges."""
    intent = QueryIntent.model_validate(intent.model_dump())
    if len(intent.model_dump_json()) > 100000:
        raise PolicyViolation("Intent exceeds structural size budget")
    if intent.ambiguities:
        raise AmbiguityError(intent.ambiguities)
    if intent.unresolved:
        raise ValidationError("Critical references remain unresolved")
    if intent.backend_hints:
        raise UnsupportedCapabilityError("Backend hints are not executable in this release")
    if len(set(intent.sources)) != len(intent.sources):
        raise PlanningError("Duplicate sources")
    sources = {s.name: s for s in schema.sources}
    if any(s not in sources for s in intent.sources):
        raise ValidationError("Unknown source or unsupported cross-backend request")
    if policy.allowed_sources is not None and any(
        s not in policy.allowed_sources for s in intent.sources
    ):
        raise PolicyViolation("Source access is not allowed")
    if intent.limit > policy.max_rows or intent.offset > policy.max_offset:
        raise PolicyViolation("Requested result bound exceeds policy")
    if len(intent.joins) > policy.max_joins:
        raise PolicyViolation("Too many joins")
    requirements = [
        (intent.joins, capabilities.joins, "joins"),
        (intent.metrics or intent.dimensions, capabilities.aggregation, "aggregation"),
        (intent.traversal, capabilities.graph_traversal, "graph traversal"),
        (intent.window, capabilities.time_series, "time windows"),
        (intent.unwind, capabilities.arrays, "array expansion"),
        (intent.calculations, capabilities.calculations, "calculations"),
        (intent.distinct, capabilities.distinct, "distinct"),
        (intent.projections, capabilities.projection, "projection"),
        (intent.sort, capabilities.sorting, "sorting"),
        (intent.offset, capabilities.offsets, "offsets"),
    ]
    for requested, supported, feature in requirements:
        if requested and not supported:
            raise UnsupportedCapabilityError(f"Backend does not support {feature}")
    if intent.traversal and intent.traversal.max_depth > policy.max_graph_depth:
        raise PolicyViolation("Traversal exceeds graph depth policy")
    if intent.operation == "aggregate" and not intent.metrics:
        raise PlanningError("Aggregate operation requires metrics")
    if intent.operation == "traverse" and not intent.traversal:
        raise PlanningError("Traverse operation requires an explicit relationship")
    edges = {r.name: r for r in schema.relationships}
    involved = {intent.sources[0]}
    for edge_name in [j.relationship for j in intent.joins] + (
        [intent.traversal.relationship] if intent.traversal else []
    ):
        if edge_name not in edges:
            raise ValidationError("Unknown relationship")
        edge = edges[edge_name]
        if edge.source not in involved and edge.target not in involved:
            raise PlanningError("Disconnected relationship would require a Cartesian product")
        if edge.source not in intent.sources or edge.target not in intent.sources:
            raise PlanningError("Both relationship endpoints must be selected")
        involved.update([edge.source, edge.target])
    if involved != set(intent.sources):
        raise UnsupportedCapabilityError(
            "Multiple sources require declared joins or traversal; federation is unsupported"
        )
    semantic_conditions: list[Filter] = []
    components: list[ConfidenceComponent] = []
    provenance: list[Provenance] = []

    def record(
        subject: str, selected: str, evidence: str, category: str = "field_selection"
    ) -> None:
        components.append(
            ConfidenceComponent(
                category=category,
                subject=subject,
                selected=selected,
                confidence=1.0,
                evidence=[evidence],
            )
        )
        provenance.append(Provenance(subject=subject, selected=selected, evidence=evidence))

    for s in intent.sources:
        record(s, s, "exact_schema_name", "source_selection")
    fields = {f"{s}.{f.name}": f for s in intent.sources for f in sources[s].fields}
    aliases = [m.alias for m in intent.metrics] + [c.alias for c in intent.calculations]
    aliases += [p.alias for p in intent.projections if p.alias]
    if intent.window:
        aliases.append(intent.window.alias)
    if len(aliases) != len(set(aliases)) or any("." in a for a in aliases):
        raise PlanningError("Output aliases must be unique simple names")

    def resolve(name: str, allow_alias: bool = False) -> str:
        if allow_alias and name in aliases:
            return name
        concepts = [(k, c) for k, c in catalog.concepts.items() if name == k or name in c.aliases]
        if len(concepts) > 1:
            raise AmbiguityError([{"term": name, "candidates": [k for k, _ in concepts]}])
        if concepts:
            _, concept = concepts[0]
            if concept.condition and concept.condition not in semantic_conditions:
                semantic_conditions.append(concept.condition)
            candidates = [
                c for c in concept.candidates if c in fields and c not in concept.deprecated
            ]
            if concept.preferred in candidates:
                candidates = [concept.preferred]
            evidence = "semantic_catalog"
        else:
            candidates = [name] if name in fields else [k for k in fields if k.endswith("." + name)]
            evidence = "exact_schema_name"
        if len(candidates) != 1:
            if candidates:
                raise AmbiguityError([{"term": name, "candidates": candidates}])
            raise ValidationError("Unresolved schema field")
        selected = candidates[0]
        record(name, selected, evidence)
        return selected

    def predicate(p: Filter | Predicate, depth: int = 0) -> dict[str, Any]:
        if depth > 12:
            raise PolicyViolation("Predicate nesting exceeds safety limit")
        if isinstance(p, Predicate):
            return {"operator": p.operator, "terms": [predicate(t, depth + 1) for t in p.terms]}
        field = resolve(p.field)
        dtype = fields[field].data_type
        op, value = p.operator, p.value
        if op == "relative_time":
            if dtype not in {"datetime", "unknown"} or not isinstance(value, str):
                raise ValidationError("Relative dates require a time field and expression")
            start, end = time_interval(value, now)
            record(value, f"[{start}, {end})", "calendar_resolution", "time_interpretation")
            return {
                "operator": "and",
                "terms": [
                    {"field": field, "operator": ">=", "value": start},
                    {"field": field, "operator": "<", "value": end},
                ],
            }
        if op in {"in", "not_in"}:
            if not isinstance(value, list) or not value or len(value) > 1000 or None in value:
                raise ValidationError("Membership requires 1..1000 non-null values")
        elif isinstance(value, list):
            raise ValidationError("List is valid only for membership predicates")
        if op in {"exists", "is_null"} and not isinstance(value, bool):
            raise ValidationError("Null/existence predicates require a boolean")
        if value is None and op not in {"=", "!="}:
            raise ValidationError("NULL requires equality or explicit null predicate")
        if op == "contains" and (
            dtype not in {"string", "array", "unknown"} or not isinstance(value, str)
        ):
            raise ValidationError("Contains requires text or an array")
        if op not in {"exists", "is_null"}:
            for v in value if isinstance(value, list) else [value]:
                if v is None:
                    continue
                if dtype in {"integer", "number"} and (
                    isinstance(v, bool) or not isinstance(v, (int, float))
                ):
                    raise ValidationError("Numeric field requires numeric values")
                if dtype == "boolean" and not isinstance(v, bool):
                    raise ValidationError("Boolean field requires boolean values")
                if dtype in {"string", "datetime"} and not isinstance(v, str):
                    raise ValidationError("Text/time field requires string values")
        record(op, field, "type_compatibility", "filter_interpretation")
        return {"field": field, "operator": op, "value": value}

    data = intent.model_dump()
    data["projections"] = [
        {"field": resolve(p.field), "alias": p.alias} for p in intent.projections
    ]
    data["dimensions"] = [resolve(d) for d in intent.dimensions]
    data["metrics"] = []
    for m in intent.metrics:
        field = "*" if m.field == "*" and m.aggregation == "count" else resolve(m.field)
        if m.aggregation in {"sum", "avg"} and fields[field].data_type not in {"number", "integer"}:
            raise ValidationError("SUM/AVG require a known numeric field")
        record(m.aggregation, field, "aggregation_type_compatibility", "aggregation_interpretation")
        data["metrics"].append({**m.model_dump(), "field": field})
    if intent.metrics and any(p["field"] not in data["dimensions"] for p in data["projections"]):
        raise PlanningError("Aggregate projections must be grouped")
    terms: list[dict[str, Any]] = [predicate(f) for f in intent.filters]
    if intent.predicate:
        terms.append(predicate(intent.predicate))
    data["filters"] = []
    data["predicate"] = (
        (
            terms[0]
            if len(terms) == 1 and "terms" in terms[0]
            else {"operator": "and", "terms": terms}
        )
        if terms
        else None
    )
    data["sort"] = [{**s.model_dump(), "field": resolve(s.field, True)} for s in intent.sort]
    if intent.metrics:
        permitted_sort = set(data["dimensions"]) | set(aliases)
        if any(s["field"] not in permitted_sort for s in data["sort"]):
            raise PlanningError("Aggregate sort must reference a group or output alias")
    data["unwind"] = [resolve(f) for f in intent.unwind]
    if any(fields[f].data_type != "array" for f in data["unwind"]):
        raise ValidationError("Unwind requires array metadata")
    data["calculations"] = [
        {**c.model_dump(), "left": resolve(c.left), "right": resolve(c.right)}
        for c in intent.calculations
    ]
    for c in data["calculations"]:
        if any(
            fields[c[side]].data_type not in {"integer", "number"} for side in ("left", "right")
        ):
            raise ValidationError("Arithmetic requires numeric fields")
    if intent.calculations and (intent.metrics or intent.dimensions):
        raise UnsupportedCapabilityError("Aggregate calculations are unsupported")
    if intent.window:
        f = resolve(intent.window.field)
        if fields[f].data_type not in {"datetime", "unknown"}:
            raise ValidationError("Window requires time metadata")
        data["window"] = {**intent.window.model_dump(), "field": f}
    for j in intent.joins:
        e = edges[j.relationship]
        if not e.source_field or not e.target_field:
            raise ValidationError("Join requires key metadata")
        resolve(f"{e.source}.{e.source_field}")
        resolve(f"{e.target}.{e.target_field}")
        record(
            j.relationship, f"{e.source} -> {e.target}", "declared_relationship", "join_selection"
        )
    if semantic_conditions:
        original = data["predicate"]
        extra = [predicate(f) for f in semantic_conditions]
        data["predicate"] = {"operator": "and", "terms": ([original] if original else []) + extra}
    ir = QueryIR.model_validate(data)
    record(intent.operation, intent.operation, "capability_validation", "intent_classification")
    operations = ["Scan"]
    for present, op in [
        (ir.joins, "Join"),
        (ir.traversal, "Traverse"),
        (ir.unwind, "Unwind"),
        (ir.predicate, "Filter"),
        (ir.window, "Window"),
        (ir.metrics or ir.dimensions, "Aggregate"),
        (ir.projections, "Project"),
        (ir.sort, "Sort"),
    ]:
        if present:
            operations.append(op)
    operations.append("Limit")
    confidence = ConfidenceAssessment(
        overall=min(c.confidence for c in components), components=components
    )
    return QueryPlan(
        ir=ir,
        nodes=[
            PlanNode.model_validate({"operation": op, "provenance": provenance})
            for op in operations
        ],
        confidence=confidence,
        provenance=provenance,
        reference_time=now.isoformat(),
    )
