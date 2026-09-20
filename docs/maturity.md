# Backend maturity

“Implemented” describes a restricted semantic subset, not exhaustive backend coverage. Contract tests exercise controlled driver or HTTP boundaries; only live integration evidence establishes behavior against an actual service. See VALIDATION.md for runs actually performed.

| Backend | Discovery | Compile / validate | Execution | Qualification |
|---|---|---|---|---|
| SQLite | Tables/views, columns/types, PK/FK; bounded catalog | SELECT, predicates, grouping, joins, aggregates, sort, distinct, arithmetic | Read-only URI, authorizer, query-only, VM deadline | Live local reference |
| PostgreSQL | One namespace, tables/views, columns, simple FK | Relational subset, named parameters | Read-only transaction, statement timeout | Live local reference; CI service |
| Generic SQL | Supplied schema | ANSI-style OFFSET/FETCH proposal | None; use a connector | Compiler only |
| Neo4j | Bounded label/property/edge sampling | Node match, bounded traversal, predicates, grouping, sort | Timed read session | Contract tests; CI service |
| MongoDB | Bounded collections and nested document sampling | Match, project, group, sort, limit, skip, unwind, distinct | Aggregation, maxTimeMS, no disk spill | Contract tests; CI service |
| Jira Cloud | Paginated bounded field metadata | JQL predicates and ordering; HTTP result limits | Enhanced `/search/jql`, bounded pagination | HTTP contract tests; external tenant not required |
| TimescaleDB | PostgreSQL plus time dimensions and continuous aggregate names | PostgreSQL plus `time_bucket` | PostgreSQL read path | Driver contract tests; live extension unavailable locally |
| InfluxDB 2 | Curated schema required; no automatic bucket discovery | Explicit Flux measurement/bucket/time window subset | Streaming query API, bounded client reads | HTTP contract tests |
| Redis | Explicit configured keys; type/module verification, no key enumeration | Hash, set sample, sorted set, stream, JSON paths, broad search | Restricted command list and socket deadlines | Driver contract tests; CI hash service |
| MySQL 8 | One database, tables/views, columns, primary/index flags | Dialect-aware SELECT subset; joins not advertised | Read-only transaction and MAX_EXECUTION_TIME | Driver contract tests |
| SAP HANA | SYS.TABLE_COLUMNS in one namespace | Isolated quoted SQL dialect, positional parameters | **Disabled** pending native safety qualification | Catalog contract tests; no live HANA |

Unknown schema identifiers, unsupported capabilities and malformed plans fail before execution. No row says “Full.” Installation of a driver is not proof of an integration.

## Explicit restrictions

- Composite foreign keys, self-joins, multiple graph edges per traversal, polymorphic graph edge types, graph relationship-property projections, Mongo `$lookup`, and federation are unsupported.
- No writes, DDL, raw expressions, stored procedures, JavaScript, Redis scripts, global Redis scans or arbitrary driver commands.
- MySQL/HANA joins are not yet advertised. PostgreSQL catalog comments/indexes/constraints and HANA views are not completely discovered.
- InfluxDB 1 (InfluxQL) and 3 (SQL) are rejected; the caller must explicitly select v2. Flux supports conjunctive filters, one metric, optional window, and mandatory half-open time bounds.
- Redis set retrieval is an unordered random sample, not deterministic paging. RedisJSON/RediSearch require the corresponding server module and supplied schema. Search currently supports bounded match-all only.
- Jira substring semantics and aggregation are rejected. Tenant-specific JQL field/operator combinations are not yet exhaustively qualified.
