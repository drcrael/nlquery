"""InfluxDB 2 Flux compiler. Version choice is explicit, never silently inferred."""

import json
from typing import Any

from nlquery.compilers.common import proposal
from nlquery.core.models import (
    CompiledQuery,
    Filter,
    Predicate,
    QueryPlan,
    QueryPolicy,
    SchemaModel,
)
from nlquery.exceptions import PolicyViolation, UnsupportedCapabilityError


class InfluxCompiler:
    def __init__(self, version: int = 2) -> None:
        if version != 2:
            raise UnsupportedCapabilityError(
                "Only InfluxDB 2 Flux is supported; v1/v3 need different compilers"
            )

    def compile(self, plan: QueryPlan, schema: SchemaModel, policy: QueryPolicy) -> CompiledQuery:
        q = plan.ir
        if (
            q.joins
            or q.traversal
            or q.unwind
            or q.calculations
            or q.distinct
            or q.offset
            or q.projections
            or len(q.metrics) > 1
        ):
            raise UnsupportedCapabilityError("Unsupported Flux query shape")
        source = next(s for s in schema.sources if s.name == q.sources[0])
        if source.kind != "measurement" or not source.bucket or not source.time_field:
            raise UnsupportedCapabilityError("Flux requires measurement, bucket and time metadata")
        filters: list[Filter] = []

        def flatten(p: Filter | Predicate) -> None:
            if isinstance(p, Filter):
                filters.append(p)
            elif p.operator == "and":
                for t in p.terms:
                    flatten(t)
            else:
                raise UnsupportedCapabilityError(
                    "Flux time-range extraction currently requires conjunctions"
                )

        if q.predicate:
            flatten(q.predicate)
        time_field = source.name + "." + source.time_field
        starts = [f for f in filters if f.field == time_field and f.operator == ">="]
        stops = [f for f in filters if f.field == time_field and f.operator == "<"]
        if len(starts) != 1 or len(stops) != 1:
            raise PolicyViolation("Flux requires exactly one inclusive start and exclusive stop")

        def literal(v: Any) -> str:
            if not isinstance(v, (str, int, float, bool)):
                raise UnsupportedCapabilityError("Unsupported Flux value")
            # Flux ${...} interpolation must not execute untrusted values.
            if isinstance(v, str) and "${" in v:
                raise UnsupportedCapabilityError(
                    "Flux interpolation sequences are not supported as values"
                )
            return json.dumps(v, ensure_ascii=False)

        text = f"from(bucket: {literal(source.bucket)}) |> range(start: time(v: {literal(starts[0].value)}), stop: time(v: {literal(stops[0].value)}))"
        text += f" |> filter(fn: (r) => r._measurement == {literal(source.name)})"
        for f in filters:
            if f in starts or f in stops:
                continue
            if f.operator not in {"=", "!=", ">", ">=", "<", "<="}:
                raise UnsupportedCapabilityError("Unsupported Flux predicate")
            name = f.field.removeprefix(source.name + ".")
            metadata = next(item for item in source.fields if item.name == name)
            if metadata.role != "tag":
                raise UnsupportedCapabilityError(
                    "Flux predicates on measurement values require a future pivot extension; only tags and ranges are supported"
                )
            text += f" |> filter(fn: (r) => r[{literal(name)}] {'==' if f.operator == '=' else f.operator} {literal(f.value)})"
        if q.window and q.window.field != time_field:
            raise UnsupportedCapabilityError("Flux window must use the measurement time field")
        if any(
            next(item for item in source.fields if source.name + "." + item.name == d).role != "tag"
            for d in q.dimensions
        ):
            raise UnsupportedCapabilityError("Flux grouping requires tag dimensions")
        if q.metrics:
            m = q.metrics[0]
            if m.field == "*":
                raise UnsupportedCapabilityError(
                    "Flux metrics require a specific measurement field"
                )
            text += f" |> filter(fn: (r) => r._field == {literal(m.field.removeprefix(source.name + '.'))})"
        text += (
            " |> group(columns: ["
            + ", ".join(literal(d.removeprefix(source.name + ".")) for d in q.dimensions)
            + "])"
        )
        if q.metrics:
            m = q.metrics[0]
            fn = "mean" if m.aggregation == "avg" else m.aggregation
            text += (
                f" |> aggregateWindow(every: {q.window.every}, fn: {fn}, createEmpty: false)"
                if q.window
                else f' |> {fn}(column: "_value")'
            )
            text += f" |> rename(columns: {{_value: {literal(m.alias)}}})"
        elif q.window:
            raise UnsupportedCapabilityError("Flux window requires an aggregate")
        text += " |> group()"
        if q.sort:
            directions = {s.direction for s in q.sort}
            if len(directions) != 1:
                raise UnsupportedCapabilityError("Mixed Flux sort directions unsupported")
            text += (
                " |> sort(columns: ["
                + ", ".join(literal(s.field.removeprefix(source.name + ".")) for s in q.sort)
                + "], desc: "
                + ("true" if q.sort[0].direction == "desc" else "false")
                + ")"
            )
        # Regroup after per-series aggregates so LIMIT is global, not per table.
        text += f" |> limit(n: {q.limit})"
        return proposal("influx", "flux", text, {}, plan)
