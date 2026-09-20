# Contributing

Use Python 3.11+. Install `.[dev,postgres,neo4j,mongo,redis,mysql,openai,anthropic,yaml]` in an isolated environment. Run Ruff check/format, mypy, pytest with coverage, build, pip check, and clean wheel/source installation checks before committing.

Preserve the probabilistic/deterministic boundary. Add an independent expected result for bug fixes, and negative tests for security boundaries. Never weaken tests to accept semantically incorrect queries. Unsupported behavior must be explicit and documented.

Use dedicated disposable databases for integration variables: NLQUERY_TEST_POSTGRES, NLQUERY_TEST_MONGO, NLQUERY_TEST_REDIS, NLQUERY_TEST_NEO4J and NLQUERY_TEST_NEO4J_PASSWORD. Tests create/reset only their dedicated fixture entities, but must not run against production. Normal tests require no paid API.

Model evaluations are opt-in and separate from deterministic CI. Include actual evidence and retained failures. Do not label driver mocks as live database coverage. Update README examples, user manual, maturity matrix and CHANGELOG with changes to public behavior.
