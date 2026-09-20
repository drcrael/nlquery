# Alpha limitations

This release completes a tested, bounded implementation through all six build phases, but does **not** satisfy every broad capability in the original production specification. The backend matrix is the supported contract.

1. HANA execution is deliberately disabled until native read-only and query deadline controls are qualified on a live system. HANA catalog discovery lacks a qualified server-side timeout.
2. InfluxDB requires a curated schema and supports Flux/v2 only. Result values remain CSV strings. Client read deadlines are not a guarantee that every remote server stops work immediately.
3. Sampled Mongo/Neo4j metadata can miss sparse fields or edge types. Supply explicit reviewed metadata for compilation; live execution rediscovers and may reject drift. Automatic index, comment, and constraint discovery is incomplete.
4. Cross-backend federation, composite joins, graph self-traversals, multiple traversal chains, relationship-property queries, Mongo lookup and aggregate calculations are unsupported.
5. The semantic catalog resolves names, aliases, preferences, and typed conditions. Units/time semantics/source metadata are descriptive; automatic unit conversions and arbitrary derived-metric formulas are not implemented.
6. Confidence measures successful deterministic grounding and capability checks. A score of 1.0 is **not** a calibrated probability that an LLM understood the user. The model must report ambiguity; not all linguistic ambiguity can be detected. No general language-accuracy claim is made.
7. Row limits bound returned rows, not scan cost, row byte size or remote query memory. Redis socket deadlines bound waiting; module behavior and remote cancellation vary. Use server quotas and least-privileged credentials.
8. Secret protection covers configured credentials and recognizable credential syntax, not arbitrary unknown secret strings embedded in user data. Applications must curate metadata and avoid logging provider/driver internals. Query parameters can contain business-sensitive data and are intentionally inspectable.
9. Safe identifiers use ASCII letters, digits, underscores and path dots; other identifier forms require a future quoting/normalization extension. SQL/Cypher text syntax differs from JQL/Flux, which do not offer equivalent bind parameters; those compilers use restricted grammar-specific literals.
10. Null/missing-field behavior differs across document, graph and SQL backends. Cross-backend conformance tests assert canonical intent equivalence, not equivalence of every native type/null/collation rule. No automatic case-insensitive collation conversion.
11. CLI live configuration supports SQLite and PostgreSQL. Other adapters use the Python API. Human-readable output currently uses indented JSON.
12. No result cache, vector retrieval, semantic cache, telemetry exporter, async execution, native EXPLAIN API or automatic multi-step semantic repair. `explain` is deterministic proposal inspection. Schema TTL caching is implemented.
13. OpenAI/Anthropic adapters need a model supporting the selected structured-output/tool protocol. Ollama model quality and context limits vary. Paid providers are contract-tested without paid inference. Live local-model smoke cases are narrow development acceptance tests, not a held-out benchmark.
14. Relative dates are resolved at minute precision using an injected UTC clock, not tenant/user locale. Store SQL timestamps consistently and configure Jira timezone consistently; tenant-specific time parsing requires qualification. Monetary arithmetic uses backend native numeric semantics; SQLite REAL is unsuitable for exact financial accounting.
15. QuerySession replaces a bounded previous intent; it does not implement arbitrary conversational analytics or year-over-year merging. Execution always validates current schema and policy.

These limitations are explicit failures or documented semantics, not placeholder implementations presented as complete features. Future releases should prioritize HANA safety qualification, stronger type/native temporal conformance, richer discovery, and expanded live backend coverage.
