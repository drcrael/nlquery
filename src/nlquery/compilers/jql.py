"""JQL rendering with allowlisted fields and grammar-specific string escaping."""

import json
import re
from datetime import datetime

from nlquery.compilers.common import proposal
from nlquery.core.models import (
    CompiledQuery,
    Filter,
    Predicate,
    QueryPlan,
    QueryPolicy,
    SchemaModel,
)
from nlquery.exceptions import UnsupportedCapabilityError


class JQLCompiler:
    def compile(self, plan: QueryPlan, schema: SchemaModel, policy: QueryPolicy) -> CompiledQuery:
        q = plan.ir
        if (
            q.metrics
            or q.dimensions
            or q.joins
            or q.traversal
            or q.window
            or q.distinct
            or q.unwind
            or q.calculations
        ):
            raise UnsupportedCapabilityError("JQL supports issue search, not arbitrary aggregation")

        def field(name: str) -> str:
            local = name.removeprefix(q.sources[0] + ".")
            custom = re.fullmatch(r"customfield_([0-9]+)", local)
            return "cf[" + custom.group(1) + "]" if custom else '"' + local + '"'

        def literal(value: object) -> str:
            if isinstance(value, bool):
                return '"true"' if value else '"false"'
            if isinstance(value, (int, float)):
                return str(value)
            text = str(value)
            if any(ord(c) < 32 for c in text):
                raise UnsupportedCapabilityError("JQL control characters are unsupported")
            return json.dumps(text, ensure_ascii=False)

        def expr(p: Filter | Predicate) -> str:
            if isinstance(p, Predicate):
                terms = [expr(t) for t in p.terms]
                return (
                    f"(NOT {terms[0]})"
                    if p.operator == "not"
                    else "(" + f" {p.operator.upper()} ".join(terms) + ")"
                )
            name, op, val = field(p.field), p.operator, p.value
            native_field = next(
                f for s in schema.sources for f in s.fields if s.name + "." + f.name == p.field
            )
            if native_field.data_type == "datetime" and isinstance(val, str):
                try:
                    parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
                except ValueError:
                    raise UnsupportedCapabilityError("JQL date requires an ISO timestamp") from None
                if parsed.second or parsed.microsecond:
                    raise UnsupportedCapabilityError("JQL date filters require minute precision")
                val = parsed.strftime("%Y-%m-%d %H:%M")
            if op in {">", ">=", "<", "<="} and native_field.data_type not in {
                "number",
                "integer",
                "datetime",
            }:
                raise UnsupportedCapabilityError(
                    "Ordered JQL comparison requires numeric/date metadata"
                )
            if op in {"is_null", "exists"} or val is None:
                null = (
                    (val if op == "is_null" else not val)
                    if op in {"is_null", "exists"}
                    else op == "="
                )
                return name + (" IS EMPTY" if null else " IS NOT EMPTY")
            if op in {"in", "not_in"}:
                assert isinstance(val, list)
                return (
                    name
                    + (" IN (" if op == "in" else " NOT IN (")
                    + ", ".join(literal(v) for v in val)
                    + ")"
                )
            if op == "contains":
                # JQL ~ is Lucene text search, not literal substring matching.
                raise UnsupportedCapabilityError("JQL literal substring semantics are unsupported")
            if op not in {"=", "!=", ">", ">=", "<", "<="}:
                raise UnsupportedCapabilityError("Unsupported JQL predicate")
            return f"{name} {op} {literal(val)}"

        query = expr(q.predicate) if q.predicate else ""
        if q.sort:
            query += " ORDER BY " + ", ".join(
                field(s.field) + " " + s.direction.upper() for s in q.sort
            )
        return proposal("jira", "jql", query.strip(), {}, plan)
