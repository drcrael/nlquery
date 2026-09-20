# Architecture

The probabilistic boundary ends at `QueryIntent`. `LLMProvider.structured_generate` produces a Pydantic-validated semantic object; raw generated database text is not a public execution input.

1. `NLQuery.interpret` applies a question-size budget and credential screening. `SchemaRetriever` selects bounded metadata, with semantic aliases strengthening lexical relevance. User request, prior intent, schema and catalog are structurally separated. Metadata is explicitly untrusted.
2. `build_plan` resolves explicit catalog mappings before schema names, detects multiple candidates and unknown references, checks numeric aggregation/type compatibility, validates declared relationships and connector capabilities, resolves relative dates to absolute half-open UTC intervals, and enforces query policy.
3. `QueryPlan` stores logical nodes, reference time, evidence-based confidence and provenance. `QueryIR` stores fully grounded executable semantics. Neither contains connection configuration.
4. Backend compilers deterministically render a read-only subset. SQL/Cypher bind values; Mongo emits structured aggregation stages; JQL/Flux use restricted literal encoders; Redis emits a restricted command array for a known key.
5. `validate` reconstructs semantics and compares the generated operation and parameters. A serialized `CompiledQuery` is a proposal, not an authorization token.
6. Each connector's `execute` independently calls `verified`, rediscovers current schema, checks policy and recompiles. Edited query text, parameters, changed schema and stricter limits invalidate the proposal. This boundary also protects callers that bypass the facade.
7. Connectors enforce native/client execution bounds and return dictionaries preserving nested values. The facade caps returned row count and rejects configured secrets in results. Backend result kind distinguishes tabular, graph, document, time-series, key/value and issue data.

Core contracts live in `core/models.py` and structural interfaces in `core/interfaces.py`. Connectors do not need core inheritance. `StaticConnector` makes offline compilation explicit and always rejects execution. Optional SDKs are imported lazily only when a live adapter or provider is used.

Relative time uses an injected clock. Query sessions retain structured state, not raw transcripts. Per-client schema caches use monotonic TTLs and explicit refresh. Structured logs include stage, request ID, backend, elapsed time and risk, never parameters by default.

Risk is a deterministic warning model, not a cost estimator. Scan/join/traversal warnings do not establish query performance. Bounded result count and bounded execution time address different risks.
