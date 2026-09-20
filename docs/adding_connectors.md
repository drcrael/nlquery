# Adding a connector

A connector supplies `backend`, `capabilities`, `compiler`, `discover()`, `execute(query, policy)`, and `secret_values()`. These are structural Python protocols; no core planner changes are required.

For a first offline implementation, reuse `StaticConnector` and an existing compiler:

```python
from nlquery import NLQuery, QueryIntent
from nlquery.connectors import StaticConnector
from nlquery.compilers.sql import SQLCompiler
from nlquery.core.models import ConnectorCapabilities, FieldSchema, SchemaModel, SourceSchema

schema = SchemaModel(
    backend="sql",
    sources=[
        SourceSchema(name="inventory", fields=[FieldSchema(name="quantity", data_type="integer")])
    ],
)
connector = StaticConnector(schema, SQLCompiler("sql"), ConnectorCapabilities(aggregation=True))
client = NLQuery(connector)
compiled = client.compile(QueryIntent(sources=["inventory"], limit=5))
assert client.validate(compiled).allowed
```

This is deliberately compile-only. To add execution:

1. Return bounded normalized metadata with `SchemaModel`. Exclude credentials and representative values. Reject budgets that cannot be honored. Document inferred/sampled fields.
2. Advertise only semantics the compiler and executor preserve. Unsupported features must raise `UnsupportedCapabilityError` before sending a request.
3. Begin `execute` with `canonical = nlquery.connectors.base.verified(self, query, policy)`. Use its query/parameters, never the caller's raw operation. This rediscovers current metadata and recompiles.
4. Execute only the verified read, with native deadline/read-only enforcement and bounded retrieval. Use a least-privileged account. Never reuse a mutable external transaction whose safety state is unknown.
5. Close cursors/connections in failure paths. Translate raw driver failures to a safe `ExecutionError` without chaining secret-bearing exception text.
6. Return dictionaries preserving backend structures. Implement a safe `repr`; `secret_values` returns configured secrets solely for boundary screening.
7. Add compiler, contract, malformed input, policy drift, timeout, injection, and opt-in real service tests. Update the maturity matrix with actual evidence.

Optional registration in your distribution:

```toml
[project.entry-points."nlquery.connectors"]
mybackend = "my_package:MyConnector"
```

Users explicitly call `nlquery.plugins.load_connector("mybackend", ...)`. Importing entry points executes installed Python; plugins are trusted application code, not untrusted model tools. Never auto-install a plugin selected by a model.
