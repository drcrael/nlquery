"""Deterministic SQL for a bounded read-only subset, with dialect parameters."""

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


class SQLCompiler:
    def __init__(self, dialect: str = "sqlite") -> None:
        self.dialect = dialect

    def compile(self, plan: QueryPlan, schema: SchemaModel, policy: QueryPolicy) -> CompiledQuery:
        q = plan.ir
        if q.traversal or q.unwind:
            raise UnsupportedCapabilityError(
                "SQL cannot compile graph traversal or array expansion"
            )
        parameters: dict[str, Any] = {}

        def bind(value: Any) -> str:
            name = f"p{len(parameters)}"
            parameters[name] = value
            if self.dialect in {"postgres", "timescaledb", "mysql"}:
                return f"%({name})s"
            if self.dialect == "hana":
                return "?"
            return ":" + name

        quote = "`" if self.dialect == "mysql" else '"'

        def ident(name: str) -> str:
            checked_name(name)
            for source in q.sources:
                if name.startswith(source + "."):
                    return quote + source + quote + "." + quote + name[len(source) + 1 :] + quote
            return ".".join(quote + p + quote for p in name.split("."))

        def expr(f: Filter | Predicate) -> str:
            if isinstance(f, Predicate):
                terms = [expr(t) for t in f.terms]
                if f.operator == "not":
                    return f"(NOT {terms[0]})"
                return "(" + f" {f.operator.upper()} ".join(terms) + ")"
            name, op, value = ident(f.field), f.operator, f.value
            if op in {"is_null", "exists"}:
                null = value if op == "is_null" else not value
                return f"{name} IS {'NULL' if null else 'NOT NULL'}"
            if value is None:
                return f"{name} IS {'NULL' if op == '=' else 'NOT NULL'}"
            if op in {"in", "not_in"}:
                assert isinstance(value, list)
                return f"{name} {'IN' if op == 'in' else 'NOT IN'} ({', '.join(bind(v) for v in value)})"
            if op == "contains":
                native = next(
                    item
                    for source in schema.sources
                    for item in source.fields
                    if source.name + "." + item.name == f.field
                )
                if native.data_type == "array":
                    raise UnsupportedCapabilityError(
                        "SQL array membership requires a native array extension"
                    )
                assert isinstance(value, str)
                escaped = value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
                return f"{name} LIKE {bind('%' + escaped + '%')} ESCAPE '!'"
            if op not in {"=", "!=", ">", ">=", "<", "<="}:
                raise UnsupportedCapabilityError("SQL predicate unsupported")
            return f"{name} {op} {bind(value)}"

        groups = [ident(d) for d in q.dimensions]
        projections = [
            ident(p.field) + (" AS " + ident(p.alias) if p.alias else "") for p in q.projections
        ]
        if q.dimensions and not projections:
            projections.extend(groups)
        if q.window:
            if self.dialect != "timescaledb":
                raise UnsupportedCapabilityError("Time bucketing requires the Timescale dialect")
            window = f"time_bucket({bind(q.window.every)}, {ident(q.window.field)})"
            projections.append(window + " AS " + ident(q.window.alias))
            groups.append(window)
        projections.extend(
            f"{m.aggregation.upper()}({'*' if m.field == '*' else ident(m.field)}) AS {ident(m.alias)}"
            for m in q.metrics
        )
        projections.extend(
            f"({ident(c.left)} {c.operator} {'NULLIF(' + ident(c.right) + ', 0)' if c.operator == '/' else ident(c.right)}) AS {ident(c.alias)}"
            for c in q.calculations
        )
        if not projections:
            # Explicit fields avoid silently leaking newly added columns at execution.
            projections = [
                ident(f"{s.name}.{f.name}")
                for s in schema.sources
                if s.name in q.sources
                for f in s.fields
            ]
        source_map = {s.name: s for s in schema.sources}

        def table(name: str) -> str:
            s = source_map[name]
            return (
                (ident(s.namespace) + "." if s.namespace else "")
                + ident(name)
                + " AS "
                + ident(name)
            )

        sql = "SELECT " + ("DISTINCT " if q.distinct else "") + ", ".join(projections)
        sql += " FROM " + table(q.sources[0])
        joined = {q.sources[0]}
        relationships = {e.name: e for e in schema.relationships}
        for join in q.joins:
            edge = relationships[join.relationship]
            target = edge.target if edge.source in joined else edge.source
            sql += f" {join.kind.upper()} JOIN {table(target)} ON {ident(edge.source + '.' + str(edge.source_field))} = {ident(edge.target + '.' + str(edge.target_field))}"
            joined.add(target)
        if q.predicate:
            sql += " WHERE " + expr(q.predicate)
        if groups:
            sql += " GROUP BY " + ", ".join(groups)
        if q.sort:
            sql += " ORDER BY " + ", ".join(
                ident(s.field) + " " + s.direction.upper() for s in q.sort
            )
        if self.dialect == "sql":
            sql += f" OFFSET {bind(q.offset)} ROWS FETCH NEXT {bind(q.limit)} ROWS ONLY"
        else:
            sql += " LIMIT " + bind(q.limit)
            if q.offset:
                sql += " OFFSET " + bind(q.offset)
        return proposal(self.dialect, "sql", sql, parameters, plan)
