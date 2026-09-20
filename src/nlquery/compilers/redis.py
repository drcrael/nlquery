"""Commands over explicitly configured keys; never KEYS, SCAN, EVAL or writes."""

from typing import Any

from nlquery.compilers.common import proposal
from nlquery.core.models import CompiledQuery, QueryPlan, QueryPolicy, SchemaModel
from nlquery.exceptions import UnsupportedCapabilityError


class RedisCompiler:
    def compile(self, plan: QueryPlan, schema: SchemaModel, policy: QueryPolicy) -> CompiledQuery:
        q = plan.ir
        if (
            q.predicate
            or q.sort
            or q.metrics
            or q.dimensions
            or q.joins
            or q.traversal
            or q.window
            or q.unwind
            or q.calculations
            or q.distinct
        ):
            raise UnsupportedCapabilityError(
                "Redis key reads do not support relational predicates or aggregation"
            )
        source = next(s for s in schema.sources if s.name == q.sources[0])
        if len(q.sources) != 1 or not source.key or source.key_type is None:
            raise UnsupportedCapabilityError("Redis requires one explicit key and its type")
        key = source.key
        fields = [p.field.removeprefix(source.name + ".") for p in q.projections]
        if any(p.alias for p in q.projections):
            raise UnsupportedCapabilityError("Redis projection aliases unsupported")
        command: list[Any]
        if source.key_type == "hash":
            if not fields or q.offset:
                raise UnsupportedCapabilityError("Hash reads require explicit bounded fields")
            command = ["HMGET", key, *fields]
        elif source.key_type == "set":
            if fields or q.offset:
                raise UnsupportedCapabilityError("Set reads cannot project or offset")
            command = ["SRANDMEMBER", key, q.limit]
        elif source.key_type == "zset":
            if fields:
                raise UnsupportedCapabilityError("Sorted set projection unsupported")
            command = ["ZRANGE", key, q.offset, q.offset + q.limit - 1, "WITHSCORES"]
        elif source.key_type == "stream":
            if fields or q.offset:
                raise UnsupportedCapabilityError("Stream reads cannot project or offset")
            command = ["XRANGE", key, "-", "+", "COUNT", q.limit]
        elif source.key_type == "json":
            if not fields or q.offset:
                raise UnsupportedCapabilityError("RedisJSON requires explicit paths without offset")
            command = ["JSON.GET", key, *["$." + f for f in fields]]
        else:
            if fields or q.offset:
                raise UnsupportedCapabilityError("Search read projection/offset unsupported")
            command = [
                "FT.SEARCH",
                key,
                "*",
                "LIMIT",
                0,
                q.limit,
                "TIMEOUT",
                max(1, int(policy.max_execution_seconds * 1000)),
            ]
        return proposal("redis", "redis_commands", command, {}, plan)
