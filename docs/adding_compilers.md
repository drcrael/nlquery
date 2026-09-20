# Adding a compiler

Implement `QueryCompiler.compile(plan, schema, policy) -> CompiledQuery`. Inputs are grounded IR and reviewed capabilities; compilation must not access a model or execute a query.

Use `compilers.common.proposal` to construct consistent explanation, risk, provenance, confidence and referenced-object fields. Implement a closed set of syntax nodes. Resolve identifiers against schema; bind data values wherever the backend supports parameters. Use grammar-specific encoders otherwise. Reject unsupported constructs instead of silently discarding them.

Execution rederives compilation and compares operations/parameters, so output must be deterministic: stable ordering, stable parameter allocation, no randomness/current timestamps, and no mutable global state. Relative dates are already absolute in the plan.

Test independent expected semantics, parameter values, field selection, boolean nesting, nulls, empty membership lists, dates, grouping, sort, offset, aliases, and error cases. Cross-backend conformance compares canonical IR; native result equivalence needs live services and separately curated type/collation cases.
