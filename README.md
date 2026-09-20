# NLQuery

**Natural language interpretation. Typed intent. Deterministic query compilation. Explicit execution.**

NLQuery uses an LLM or another semantic parser to produce a typed query intent. It then grounds schema references, constructs an inspectable logical plan, compiles backend operations, and validates them independently of the model. Models do not supply executable database syntax.

```text
Question -> bounded schema retrieval -> typed intent -> semantic grounding
         -> logical plan -> canonical IR -> compiler -> validation/policy
         -> explicit execution -> normalized results
```

**v0.1.0a1 is an alpha, not a claim of complete production support for every backend.** Read the [maturity matrix](docs/maturity.md), [limitations](LIMITATIONS.md), and [validation evidence](VALIDATION.md). HANA execution is intentionally disabled. InfluxDB 1/3 and cross-backend federation are unsupported.

## Install

Python 3.11 or newer. Install the wheel from this repository's GitHub release, or install the tagged source:

```bash
python -m pip install "git+https://github.com/drcrael/nlquery.git@v0.1.0a1"
# PostgreSQL and a local model:
python -m pip install "nlquery[postgres,ollama] @ git+https://github.com/drcrael/nlquery.git@v0.1.0a1"
```

No PyPI publication is implied. Core installation requires Pydantic only; SQLite uses the standard library. Optional extras: `postgres`, `mysql`, `neo4j`, `mongo`, `redis`, `influx`, `hana`, `jira`, `openai`, `anthropic`, `ollama`, `yaml`, `all`.

## Quick start without a database or LLM

```python
from nlquery import NLQuery, QueryIntent
from nlquery.cli.main import offline
from nlquery.core.models import FieldSchema, Filter, SchemaModel, SourceSchema

schema = SchemaModel(
    backend="sqlite",
    sources=[SourceSchema(name="orders", fields=[FieldSchema(name="status", data_type="string")])],
)
client = NLQuery(offline(schema))
compiled = client.compile(
    QueryIntent(sources=["orders"], filters=[Filter(field="status", value="paid")], limit=10)
)
print(compiled.generated_query)
print(compiled.parameters)
assert client.validate(compiled).allowed
```

This example is executable in [examples/compile_only.py](examples/compile_only.py). A typed intent needs no model access. `StaticConnector` deliberately refuses execution.

## Natural language and explicit execution

```python
from nlquery import NLQuery
from nlquery.connectors import PostgresConnector
from nlquery.llm.providers import OllamaProvider

client = NLQuery(
    PostgresConnector.from_env("DATABASE_URL"),
    llm=OllamaProvider(model="qwen3"),
)
proposal = client.ask("Show the ten newest orders")  # compile only
print(proposal.explanation)
print(proposal.provenance)
result = client.execute(proposal)  # explicit execution
# Equivalent convenience path: client.ask(question, execute=True)
```

The database schema must support the requested concepts. Ambiguity and unsupported features raise structured project errors; no best-effort query is silently substituted. Use a least-privileged read-only database account.

The complete [ecommerce example](examples/ecommerce.py) creates `customers`, `orders`, `order_items`, and `products`; interprets the previous-quarter revenue request using an explicit mock; compiles a parameterized join/aggregate; and checks exact returned totals. Mock results verify deterministic software, not natural-language accuracy.

## Semantic catalog

```python
from nlquery.core.models import SemanticCatalog, SemanticConcept

catalog = SemanticCatalog(
    concepts={"revenue": SemanticConcept(candidates=["orders.total_amount"], units="USD")}
)
```

Pass `catalog=catalog` to `NLQuery`. Exact concepts and aliases take precedence over schema names. Multiple available candidates cause clarification unless an explicit preferred candidate disambiguates them. Provenance records the selected mapping.

## CLI

```bash
nlquery inspect --backend sqlite --database shop.db --format json
nlquery compile --backend sqlite --database shop.db --intent intent.json --format json
nlquery explain --schema schema.json --intent intent.json
nlquery validate --database shop.db --compiled proposal.json
nlquery ask --backend postgres --connection-env DATABASE_URL --llm ollama:qwen3 "Show ten orders"
nlquery ask --database shop.db --llm ollama:qwen3 --execute "Show ten orders"
```

`--schema` provides offline compilation for all advertised compilers. The CLI's live connection factory currently handles SQLite and PostgreSQL; use the Python API for other live adapters. `compile` and `explain` reject `--execute`. Exit status 2 means validation, configuration, or execution failed.

## Security and development

Read-only operations, schema allowlisting, parameterized SQL/Cypher, finite graph depth, bounded results, bounded metadata, explicit execution, native deadlines where supported, safe error messages, and execution-time recompilation are enforced independently of the LLM. Model context never includes connector configuration. Known configured secrets and credential-shaped strings are rejected from public artifacts. This is not a universal secret detector; see [security](SECURITY.md).

```bash
python -m pip install -e ".[dev,postgres,neo4j,mongo,redis,mysql,openai,anthropic,yaml]"
ruff check .
ruff format --check .
mypy src
pytest --cov=nlquery
python -m build
```

Normal tests require no paid API. Live service tests opt in through `NLQUERY_TEST_*` variables; CI supplies disposable PostgreSQL, MongoDB, Redis, and Neo4j services. [Model evaluations](docs/evaluation.md) are separate from deterministic tests.

## Documentation

- [User manual](docs/user_manual.md)
- [Architecture](docs/architecture.md) and [security](docs/security.md)
- [Backend maturity](docs/maturity.md) and [limitations](LIMITATIONS.md)
- [Semantic catalog](docs/semantic_catalog.md)
- [Adding connectors](docs/adding_connectors.md) and [compilers](docs/adding_compilers.md)
- [Examples](docs/examples.md), [contributing](CONTRIBUTING.md), and [changelog](CHANGELOG.md)

MIT licensed.
