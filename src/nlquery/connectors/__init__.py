"""Connectors load drivers lazily; importing these names does not connect."""

from nlquery.connectors.hana import HANAConnector
from nlquery.connectors.influxdb import InfluxDBConnector
from nlquery.connectors.jira import JiraConnector
from nlquery.connectors.mongodb import MongoDBConnector
from nlquery.connectors.mysql import MySQLConnector
from nlquery.connectors.neo4j import Neo4jConnector
from nlquery.connectors.postgres import PostgresConnector
from nlquery.connectors.redis import RedisConnector
from nlquery.connectors.sqlite import SQLiteConnector
from nlquery.connectors.static import StaticConnector
from nlquery.connectors.timescaledb import TimescaleDBConnector

__all__ = [
    "SQLiteConnector",
    "PostgresConnector",
    "Neo4jConnector",
    "MongoDBConnector",
    "JiraConnector",
    "RedisConnector",
    "InfluxDBConnector",
    "TimescaleDBConnector",
    "MySQLConnector",
    "HANAConnector",
    "StaticConnector",
]
