"""Bounded graph matching and aggregation; no procedures or raw Cypher input."""

from typing import Any

from nlquery.compilers.common import proposal
from nlquery.core.models import (
    CompiledQuery,
    Filter,
    Predicate,
    QueryPlan,
    QueryPolicy,
    SchemaModel,
    checked_name,
)
from nlquery.exceptions import UnsupportedCapabilityError


class CypherCompiler:
    def compile(self, plan: QueryPlan, schema: SchemaModel, policy: QueryPolicy) -> CompiledQuery:
        q = plan.ir
        if q.joins or q.unwind or q.window or q.calculations:
            raise UnsupportedCapabilityError("Unsupported graph construct")
        params: dict[str, Any] = {}

        def bind(v: Any) -> str:
            key = f"p{len(params)}"
            params[key] = v
            return "$" + key

        def ident(v: str) -> str:
            checked_name(v)
            return ".".join("`" + t + "`" for t in v.split("."))

        def node(s: str) -> str:
            return f"({ident(s)}:{ident(s)})"

        def expr(p: Filter | Predicate) -> str:
            if isinstance(p, Predicate):
                parts = [expr(t) for t in p.terms]
                return (
                    "(NOT " + parts[0] + ")"
                    if p.operator == "not"
                    else "(" + f" {p.operator.upper()} ".join(parts) + ")"
                )
            name, op, val = ident(p.field), p.operator, p.value
            if op in {"is_null", "exists"} or val is None:
                null = (
                    (val if op == "is_null" else not val)
                    if op in {"is_null", "exists"}
                    else op == "="
                )
                return f"{name} IS {'NULL' if null else 'NOT NULL'}"
            if op == "contains":
                native = next(
                    f for s in schema.sources for f in s.fields if s.name + "." + f.name == p.field
                )
                if native.data_type == "array":
                    return f"{bind(val)} IN {name}"
            if op == "not_in":
                return f"NOT ({name} IN {bind(val)})"
            ops = {
                "=": "=",
                "!=": "<>",
                ">": ">",
                ">=": ">=",
                "<": "<",
                "<=": "<=",
                "in": "IN",
                "contains": "CONTAINS",
            }
            if op not in ops:
                raise UnsupportedCapabilityError("Unsupported Cypher predicate")
            return f"{name} {ops[op]} {bind(val)}"

        match = node(q.sources[0])
        if q.traversal:
            t = q.traversal
            edge = next(e for e in schema.relationships if e.name == t.relationship)
            target = edge.target if edge.source == q.sources[0] else edge.source
            if t.max_depth > policy.max_graph_depth:
                raise UnsupportedCapabilityError("Traversal exceeds policy")
            link = f"[:{ident(edge.name)}*{t.min_depth}..{t.max_depth}]"
            match += (
                "-" + link + "->"
                if t.direction == "out"
                else "<-" + link + "-"
                if t.direction == "in"
                else "-" + link + "-"
            ) + node(target)
        query = "MATCH " + match
        if q.predicate:
            query += " WHERE " + expr(q.predicate)
        projections = [
            ident(p.field) + (" AS " + ident(p.alias) if p.alias else "") for p in q.projections
        ]
        if q.dimensions and not projections:
            projections = [ident(d) for d in q.dimensions]
        projections += [
            f"{m.aggregation}({'*' if m.field == '*' else ident(m.field)}) AS {ident(m.alias)}"
            for m in q.metrics
        ]
        if not projections:
            projections = [ident(s) for s in q.sources]
        query += " RETURN " + ("DISTINCT " if q.distinct else "") + ", ".join(projections)
        if q.sort:
            query += " ORDER BY " + ", ".join(
                ident(s.field) + " " + s.direction.upper() for s in q.sort
            )
        if q.offset:
            query += " SKIP " + bind(q.offset)
        query += " LIMIT " + bind(q.limit)
        return proposal("neo4j", "cypher", query, params, plan)
