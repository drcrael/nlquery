# Examples

Run `python examples/compile_only.py` for a zero-network proposal. Run `python examples/ecommerce.py` for the full mock-to-SQLite acceptance scenario with independently asserted customer totals.

Backend compilers are selectable offline through `nlquery.cli.main.offline(schema)`. Set `schema.backend` to `sql`, `sqlite`, `postgres`, `mysql`, `hana`, `timescaledb`, `neo4j`, `mongo`, `jira`, `influx`, or `redis`. Source metadata must represent native semantics: node labels/edges, collection paths, measurement bucket/time metadata, or explicit Redis key/type. See unit fixtures for complete examples.

Use the public connectors from `nlquery.connectors` for live access. Drivers are optional; construction performs no connection. `PostgresConnector.from_env()` reads DATABASE_URL; other adapters accept explicit credentials separately from schema/catalog/LLM data. Never paste connection strings into natural-language questions.

`QuerySession(client).ask(...)` sends the previous typed intent rather than raw history. The provider returns a complete replacement intent and it undergoes all normal validation. It never implicitly executes.
