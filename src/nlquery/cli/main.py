"""Credential-safe CLI. Query execution requires the --execute flag."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from nlquery import NLQuery, QueryIntent
from nlquery.compilers.cypher import CypherCompiler
from nlquery.compilers.influx import InfluxCompiler
from nlquery.compilers.jql import JQLCompiler
from nlquery.compilers.mongo import MongoCompiler
from nlquery.compilers.redis import RedisCompiler
from nlquery.compilers.sql import SQLCompiler
from nlquery.config import QueryConfig, load_catalog
from nlquery.connectors.postgres import PostgresConnector
from nlquery.connectors.sqlite import SQLiteConnector
from nlquery.connectors.static import StaticConnector
from nlquery.core.interfaces import Connector, QueryCompiler
from nlquery.core.models import CompiledQuery, ConnectorCapabilities, SchemaModel
from nlquery.exceptions import ConfigurationError, NLQueryError
from nlquery.guardrails.secrets import ensure_safe


def offline(schema: SchemaModel) -> StaticConnector:
    backend = schema.backend
    compilers: dict[str, QueryCompiler] = {
        "neo4j": CypherCompiler(),
        "mongo": MongoCompiler(),
        "jira": JQLCompiler(),
        "influx": InfluxCompiler(),
        "redis": RedisCompiler(),
    }
    compiler = compilers.get(backend, SQLCompiler(backend))
    caps = ConnectorCapabilities(
        joins=backend in {"sqlite", "postgres", "sql", "timescaledb"},
        aggregation=backend not in {"jira", "redis"},
        graph_traversal=backend == "neo4j",
        time_series=backend in {"timescaledb", "influx"},
        arrays=backend == "mongo",
        calculations=backend in {"sqlite", "postgres", "mysql", "hana", "timescaledb", "sql"},
        distinct=backend not in {"jira", "redis", "influx"},
        projection=backend != "influx",
        sorting=backend != "redis",
        offsets=backend not in {"jira", "influx"},
    )
    if backend not in {*compilers, "sqlite", "postgres", "mysql", "hana", "timescaledb", "sql"}:
        raise ConfigurationError("Unknown backend")
    return StaticConnector(schema, compiler, caps)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="nlquery",
        description="Compile typed or natural-language requests; execute only explicitly.",
    )
    parser.add_argument("command", choices=["inspect", "compile", "ask", "explain", "validate"])
    parser.add_argument("question", nargs="?")
    parser.add_argument("--backend", default="sqlite")
    parser.add_argument("--database")
    parser.add_argument("--connection-env", default="DATABASE_URL")
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--intent", type=Path)
    parser.add_argument("--compiled", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--llm")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args(argv)
    try:
        if args.execute and args.command != "ask":
            raise ConfigurationError(
                "Only ask accepts --execute; compile/explain are read-only proposals"
            )
        cfg = QueryConfig.load(args.config)
        connector: Connector
        if args.schema:
            connector = offline(SchemaModel.model_validate_json(args.schema.read_text()))
        elif args.backend == "sqlite" and args.database:
            connector = SQLiteConnector(args.database, discovery=cfg.discovery)
        elif args.backend == "postgres":
            connector = PostgresConnector.from_env(args.connection_env)
        else:
            raise ConfigurationError(
                "Provide --schema for offline compilation or configure SQLite/PostgreSQL"
            )
        client = NLQuery(
            connector,
            llm=args.llm or os.getenv("NLQUERY_LLM"),
            policy=cfg.policy,
            discovery=cfg.discovery,
            catalog=load_catalog(args.catalog) if args.catalog else None,
        )
        if args.command == "inspect":
            output = client.schema().model_dump(mode="json")
        elif args.command == "validate":
            if not args.compiled:
                raise ConfigurationError("validate requires --compiled")
            query = CompiledQuery.model_validate_json(args.compiled.read_text())
            validation = client.validate(query)
            output = validation.model_dump()
            print(json.dumps(output, indent=2))
            return 0 if validation.allowed else 2
        else:
            value = (
                QueryIntent.model_validate_json(args.intent.read_text())
                if args.intent
                else args.question
            )
            if not value:
                raise ConfigurationError("Provide a question or --intent")
            query = client.compile(value)
            if args.command == "explain":
                output = client.explain(query)
            elif args.execute:
                output = client.execute(query).model_dump(mode="json")
            else:
                output = query.model_dump(mode="json")
        ensure_safe(output, connector.secret_values())
        print(
            json.dumps(output, indent=2, default=str)
            if args.format == "json"
            else json.dumps(output, indent=2, default=str)
        )
        return 0
    except (NLQueryError, ValueError, OSError):
        print(
            "NLQuery: request failed validation, configuration, or execution; no raw backend details are exposed.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
