# Release validation

## Source and package gates

- Linux / Python 3.12.14: **238 passed, 4 optional live-service tests skipped**, **86.93% coverage** (minimum 85%).
- Ruff lint/format and mypy pass across all 42 library modules. Wheel and source distributions build; dependency checks pass.
- A separate disposable PostgreSQL run: **239 passed, 3 skipped**. SQLite and PostgreSQL discovery, parameter binding, execution and exact returned values were exercised locally.
- Clean wheel and source installations each passed **238 tests, 4 optional service skips** outside the source checkout, plus dependency checks and the ecommerce example.
- [Cross-platform and service qualification](https://github.com/drcrael/nlquery/actions/runs/35483380663) passed all seven jobs at `f23a460`: Linux, Windows and macOS with Python 3.11/3.14, and Linux with real PostgreSQL 17, MongoDB 8, Redis 7 and Neo4j 5 services. The service job passed **242 tests, no skips, 87.59% coverage**.
- [Initial CI failures](https://github.com/drcrael/nlquery/actions/runs/35481866496) exposed a Windows example database-handle leak and macOS builds without SQLite extension-loading support. Both defects were fixed, with a regression proving read-only operation when extension loading is absent. Subsequent qualification passed on both platforms. Intermediate publication commits also ran the old source and retained those failures; the linked successful run tests the corrected source.
- Local container startup was attempted but the sandbox blocks user namespace creation. Remote real-service results above replace those local skips; they are not mock-driver results.

## Semantic and security evidence

**50 golden NL requests** replay expected structured intents through an explicit mock. Cross-backend tests compare canonical plans. These deterministic tests are not measurements of model inference accuracy.

Property tests exercise arbitrary values and limits. Security tests cover untrusted metadata, malicious literals, mutation-shaped output, unknown sources/fields, credential leakage, logging, bounded repair, execution-policy changes and tampered proposals. Values are bound where supported; JQL/Flux use restricted literal encoders. Execution revalidates schema, capabilities, policy and canonical compiled operations independently.

The ecommerce acceptance example creates all four requested tables, resolves revenue through the semantic catalog, joins customers and orders, resolves the previous quarter, excludes cancelled orders, executes parameterized SQLite SQL and checks exact totals. [Machine-readable evidence](docs/acceptance-ecommerce.json). Its interpreter is explicitly a mock fixture.

## Actual model inference

**Final Qwen 2.5 7B result: 2/2 passed**, with every raw intent metric true, canonical plans identical, and exact SQLite rows correct. [Successful actual inference run](https://github.com/drcrael/nlquery/actions/runs/35483394665) at `f23a460`; [retained machine-readable report](docs/evidence/final-live-model.json). The complete run took about seven minutes on CPU, including installation and model download.

Two Qwen 2.5 3B development runs failed both smoke cases: [initial run](https://github.com/drcrael/nlquery/actions/runs/35481888760), [after general interpretation guidance](https://github.com/drcrael/nlquery/actions/runs/35482476538). Comparison handling improved, but requested projections were still omitted. [Retained initial report](docs/evidence/initial-live-model.json). These failures are not counted as successful semantic evaluation. Qwen 3B is not qualified by this release.

[The initial 7B run](https://github.com/drcrael/nlquery/actions/runs/35482627181) also failed both cases because it added an unrequested sort column to the output. General projection instructions were clarified; the same expected intents and exact-row assertions were retained.

[Two subsequent runs](https://github.com/drcrael/nlquery/actions/runs/35482974783) stopped before inference because Ollama had not started on runners without systemd. Explicit loopback server startup and a bounded readiness check were added. Infrastructure failures are excluded from accuracy results.

[Another 7B attempt](https://github.com/drcrael/nlquery/actions/runs/35483151366) omitted projections and emitted unsupported backend hints. The Ollama adapter was then corrected to include the complete response schema in the prompt as well as the transport format, following [Ollama guidance](https://docs.ollama.com/capabilities/structured-outputs), with a transport regression assertion.

The evaluation retains raw intent metrics separately from canonical-plan agreement and exact execution results. Equivalent qualification or predicate representations may differ in raw metrics; canonical equivalence and exact rows are both required. These two development cases are not a held-out benchmark or a general language-accuracy claim.

## Manual and published artifacts

The manual is available in Markdown and a 13-page PDF. All pages were rendered and inspected. Embedded fonts corrected a rendering defect detected in the initial PDF candidate.

The published-artifact workflow downloads the release wheel, source archive, PDF and SHA256SUMS. Each of six OS/Python combinations checks checksums and installs/tests both wheel and source outside the checkout (12 independent package installations). See the release's linked workflow results for the exact published bytes; workflow definitions alone are not successful evidence.

## Unavailable integrations and scope

MySQL, HANA catalog discovery, TimescaleDB metadata, Jira pagination and InfluxDB transport have driver/HTTP contract tests, not live-service qualification. HANA execution is disabled. Paid OpenAI/Anthropic adapters use actual SDKs with mocked HTTP transports; no paid inference was performed. Unsupported behavior and incomplete discovery are detailed in [LIMITATIONS.md](LIMITATIONS.md) and the [backend maturity matrix](docs/maturity.md). This is an alpha release, not completion of every broad production capability in the original specification.

## Post-publication verification

[Exact published artifact verification](https://github.com/drcrael/nlquery/actions/runs/35483846331) passed **all six jobs**: Linux, Windows and macOS with Python 3.11 and 3.14. Each job downloaded the release assets, checked SHA256SUMS, and tested both the wheel and source distribution in fresh environments outside the checkout: **12 successful installations**, each with **238 passed and 4 optional live-service skips**, dependency checks, and the executable ecommerce example. The separate service gate covers those live-service skips.

An independent download also verified all three asset checksums against the published manifest. The release remains tagged at `74e3f68`; this evidence update does not replace the verified release bytes.

Tag creation triggered the obsolete one-time source-import workflow, which failed because its staging archive had already been consumed. This was a publication-helper failure, not a library or artifact-test failure. The importer was retired from main after publication; its history and the [failed helper run](https://github.com/drcrael/nlquery/actions/runs/35483846184) remain available. The regular validation, live-model evaluation and release-artifact workflows remain active.
