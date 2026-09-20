"""Structured aggregation pipeline compiler, with no JavaScript or executable strings."""

import re
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
from nlquery.exceptions import UnsupportedCapabilityError


class MongoCompiler:
    def compile(self, plan: QueryPlan, schema: SchemaModel, policy: QueryPolicy) -> CompiledQuery:
        q = plan.ir
        if q.joins or q.traversal or q.window or q.calculations or len(q.sources) != 1:
            raise UnsupportedCapabilityError(
                "Mongo lookup/window/calculation semantics are unsupported"
            )

        def field(name: str) -> str:
            return name.removeprefix(q.sources[0] + ".")

        def expr(p: Filter | Predicate) -> dict[str, Any]:
            if isinstance(p, Predicate):
                return {
                    "$nor" if p.operator == "not" else "$" + p.operator: [expr(t) for t in p.terms]
                }
            key, op, value = field(p.field), p.operator, p.value
            if op == "exists":
                return {key: {"$exists": value}}
            if op == "is_null":
                return {key: {"$eq" if value else "$ne": None}}
            if op == "contains":
                native = next(
                    f for s in schema.sources for f in s.fields if s.name + "." + f.name == p.field
                )
                return (
                    {key: {"$eq": value}}
                    if native.data_type == "array"
                    else {key: {"$regex": re.escape(str(value))}}
                )
            ops = {
                "=": "$eq",
                "!=": "$ne",
                ">": "$gt",
                ">=": "$gte",
                "<": "$lt",
                "<=": "$lte",
                "in": "$in",
                "not_in": "$nin",
            }
            if op not in ops:
                raise UnsupportedCapabilityError("Unsupported Mongo predicate")
            return {key: {ops[op]: value}}

        pipeline: list[dict[str, Any]] = []
        for name in q.unwind:
            pipeline.append({"$unwind": "$" + field(name)})
        if q.predicate:
            pipeline.append({"$match": expr(q.predicate)})
        grouped = bool(q.metrics or q.dimensions or q.distinct)
        output_fields: dict[str, str] = {}
        if grouped:
            dims = q.dimensions or ([p.field for p in q.projections] if q.distinct else [])
            if q.distinct and not dims:
                raise UnsupportedCapabilityError("Mongo distinct requires explicit projections")
            group: dict[str, Any] = {
                "_id": {f"g{i}": "$" + field(d) for i, d in enumerate(dims)} if dims else None
            }
            project: dict[str, Any] = {"_id": 0}
            for i, d in enumerate(dims):
                name = next(
                    (p.alias for p in q.projections if p.field == d and p.alias), None
                ) or field(d).replace(".", "_")
                project[name] = f"$_id.g{i}"
                output_fields[d] = name
            for m in q.metrics:
                if m.aggregation == "count":
                    group[m.alias] = {
                        "$sum": 1
                        if m.field == "*"
                        else {
                            "$cond": [
                                {"$ne": [{"$ifNull": ["$" + field(m.field), None]}, None]},
                                1,
                                0,
                            ]
                        }
                    }
                else:
                    group[m.alias] = {"$" + m.aggregation: "$" + field(m.field)}
                project[m.alias] = 1
                output_fields[m.alias] = m.alias
            pipeline += [{"$group": group}, {"$project": project}]
        if q.sort:
            pipeline.append(
                {
                    "$sort": {
                        output_fields.get(s.field, field(s.field)): 1
                        if s.direction == "asc"
                        else -1
                        for s in q.sort
                    }
                }
            )
        if q.offset:
            pipeline.append({"$skip": q.offset})
        pipeline.append({"$limit": q.limit})
        if q.projections and not grouped:
            pipeline.append(
                {
                    "$project": {
                        "_id": 0,
                        **{p.alias or field(p.field): "$" + field(p.field) for p in q.projections},
                    }
                }
            )
        return proposal("mongo", "mongodb_pipeline", pipeline, {}, plan)
