# Security policy

Report vulnerabilities privately through the repository owner's GitHub contact/security advisory mechanism. Do not place real credentials, customer records or exploitable production connection details in public issues.

Supported security updates currently target the latest alpha. NLQuery is not a substitute for backend authorization, tenant isolation, read-only credentials or server resource quotas.

## Trust boundaries

- Treat user requests, model output, catalog descriptions, database comments and issue/document content as untrusted data.
- Never use LLM confidence as execution authorization.
- Core intent has no mutation operation or arbitrary code/query field. Extra fields are rejected.
- Connector execution revalidates current schema/policy and recompiles before dispatch. Edited serialized proposals are not trusted.
- SQL/Cypher values are parameterized. Identifiers are schema-grounded and constrained. Mongo pipelines are generated objects, never JavaScript. Redis accepts no raw commands from model output.
- Enforce source allowlists independently at planning and execution. Graph depth, joins, offsets and result limits have hard bounds.
- Keep credentials only in connector/provider configuration, environment variables or an application secret manager. Safe representations and errors suppress connection details. Known secrets and credential-shaped strings are rejected from artifacts; arbitrary unknown secrets cannot be reliably recognized.
- Use least-privileged backend accounts. Compile-only may read schema metadata unless a static schema is supplied. It does not execute the proposed query.

## Operational considerations

Do not enable debug logging in third-party SDKs against sensitive infrastructure without reviewing their output. Query proposals include parameter values by design; store them as sensitive business artifacts where applicable. No telemetry is sent by the core library.

Native timeouts are used for SQLite, PostgreSQL/Timescale, Neo4j, MongoDB and MySQL. Jira/Influx/Redis use bounded transport reads plus operation/result restrictions. Timeout/cancellation behavior of remote systems differs. HANA execution remains disabled.

See [limitations](LIMITATIONS.md) for discovery sampling, response byte-size limits, secret detection and server-side enforcement caveats. The dedicated security and property suites are part of release validation.
