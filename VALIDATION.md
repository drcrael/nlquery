# Release validation

## Local source gate

- Linux / Python 3.12.14: **237 passed, 4 optional live-service tests skipped** in the default environment. Coverage is recorded in the release evidence below; the configured minimum is 85%.
- Ruff lint/format and mypy pass. All 42 library modules have checked type annotations. Wheel and source distributions build successfully. `pip check` passes.
- A separate run using a disposable PostgreSQL binary executes the real PostgreSQL test: **238 passed, 3 skipped**. SQLite and PostgreSQL discovery, parameter binding, execution and expected returned values were actually exercised.
- Local container startup was attempted; the sandbox blocks user namespace creation. MongoDB, Neo4j and Redis live tests remain explicitly skipped locally and are configured as real services in CI.
- **50 golden NL requests** replay expected structured intents through an explicit mock. Cross-backend tests compare canonical plans. These are deterministic software tests, not model inference accuracy.
- Property tests exercise arbitrary values and limits; security tests exercise untrusted metadata, malicious literal values, mutation-shaped outputs, unknown sources/fields, credential leakage, safe logging, bounded repair and tampered proposals.
- The ecommerce acceptance example creates all four requested tables, resolves revenue through a semantic catalog, joins customers and orders, resolves the previous quarter, excludes cancelled orders, executes parameterized SQLite SQL and checks exact customer totals. [Machine-readable evidence](docs/acceptance-ecommerce.json).

## Packaging and manual

Isolated wheel and source installations are validated outside the source checkout. The initial candidate passed 234 tests with four optional live-service skips in each clean environment; the final candidate adds three focused date/array regression tests and is rerun before release. Both environments run the ecommerce example and dependency checks.

The user manual is provided in Markdown and a 13-page PDF. Every PDF page was rendered and visually checked for clipping, layout and legibility.

## Remote qualification

The repository includes six portable CI combinations (Linux, Windows, macOS; Python 3.11/3.14), a Linux real-service job (PostgreSQL, MongoDB, Redis, Neo4j), a separate opt-in live Ollama evaluation, and an exact-published-artifact workflow. Actual run outcomes will be recorded after those gates complete. Workflow definitions alone are not successful test evidence.

## Evidence boundaries

Driver/HTTP contracts cover MySQL, HANA catalog discovery, TimescaleDB metadata, Jira pagination and InfluxDB transport without requiring paid/external services. These are not live service results. HANA execution is disabled. Paid LLM adapters are exercised through actual SDKs with mocked HTTP transports; no paid inference was performed. See LIMITATIONS.md and docs/maturity.md for unsupported behavior.
