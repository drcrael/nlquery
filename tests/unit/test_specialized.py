import pytest

from nlquery import NLQuery, QueryIntent
from nlquery.compilers.influx import InfluxCompiler
from nlquery.compilers.redis import RedisCompiler
from nlquery.compilers.sql import SQLCompiler
from nlquery.connectors.static import StaticConnector
from nlquery.core.models import (
    ConnectorCapabilities,
    FieldSchema,
    Filter,
    Metric,
    Projection,
    SchemaModel,
    SourceSchema,
    TimeWindow,
)
from nlquery.exceptions import PolicyViolation, UnsupportedCapabilityError


@pytest.mark.parametrize(
    "kind,cmd",
    [
        ("hash", "HMGET"),
        ("set", "SRANDMEMBER"),
        ("zset", "ZRANGE"),
        ("stream", "XRANGE"),
        ("json", "JSON.GET"),
        ("search", "FT.SEARCH"),
    ],
)
def test_redis(kind, cmd):
    schema = SchemaModel(
        backend="redis",
        sources=[
            SourceSchema(
                name="cache",
                kind="key",
                key="app:items",
                key_type=kind,
                fields=[FieldSchema(name="name")],
            )
        ],
    )
    client = NLQuery(StaticConnector(schema, RedisCompiler(), ConnectorCapabilities(sorting=False)))
    q = client.compile(
        QueryIntent(
            sources=["cache"],
            projections=[Projection(field="name")] if kind in {"hash", "json"} else [],
            limit=3,
        )
    )
    assert q.query[0] == cmd
    assert q.query[1] == "app:items"
    assert client.validate(q).allowed
    with pytest.raises(UnsupportedCapabilityError):
        client.compile(QueryIntent(sources=["cache"], filters=[Filter(field="name", value="*")]))


def influx():
    schema = SchemaModel(
        backend="influx",
        sources=[
            SourceSchema(
                name="cpu",
                kind="measurement",
                bucket="metrics",
                time_field="time",
                fields=[
                    FieldSchema(name="time", data_type="datetime"),
                    FieldSchema(name="usage", data_type="number"),
                ],
            )
        ],
    )
    return NLQuery(
        StaticConnector(
            schema,
            InfluxCompiler(),
            ConnectorCapabilities(
                aggregation=True, time_series=True, projection=False, offsets=False
            ),
        )
    )


def test_flux_window():
    client = influx()
    q = client.compile(
        QueryIntent(
            sources=["cpu"],
            filters=[Filter(field="time", operator="relative_time", value="last_7_days")],
            metrics=[Metric(field="usage", aggregation="avg", alias="mean_usage")],
            window=TimeWindow(field="time", every="5m"),
        )
    )
    assert "aggregateWindow(every: 5m, fn: mean" in q.query
    assert client.validate(q).allowed


def test_flux_requires_time_range():
    with pytest.raises(PolicyViolation):
        influx().compile(QueryIntent(sources=["cpu"]))


@pytest.mark.parametrize("version", [1, 3])
def test_version(version):
    with pytest.raises(UnsupportedCapabilityError):
        InfluxCompiler(version)


def test_timescale():
    schema = SchemaModel(
        backend="timescaledb",
        sources=[
            SourceSchema(
                name="cpu",
                fields=[
                    FieldSchema(name="time", data_type="datetime"),
                    FieldSchema(name="usage", data_type="number"),
                ],
            )
        ],
    )
    client = NLQuery(
        StaticConnector(
            schema,
            SQLCompiler("timescaledb"),
            ConnectorCapabilities(aggregation=True, time_series=True),
        )
    )
    q = client.compile(
        QueryIntent(
            sources=["cpu"],
            metrics=[Metric(field="usage", aggregation="avg", alias="mean")],
            window=TimeWindow(field="time", every="5m"),
        )
    )
    assert "time_bucket(%(p0)s" in q.query
    assert client.validate(q).allowed
