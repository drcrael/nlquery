# Semantic catalog

Construct `SemanticCatalog(concepts={...})` or load JSON/YAML with `nlquery.config.load_catalog`; YAML requires the `yaml` extra and uses a safe parser. No catalog string is evaluated as code.

```json
{
  "concepts": {
    "revenue": {
      "description": "Recognized revenue",
      "candidates": ["orders.total_amount", "invoices.recognized_amount"],
      "preferred": "orders.total_amount",
      "aliases": ["sales"],
      "units": "USD"
    }
  }
}
```

Only candidates present in the query's selected sources participate. Deprecated candidates are removed; an available preferred candidate resolves ambiguity. A single remaining mapping produces deterministic evidence. Zero candidates fails as unresolved; multiple candidates return structured ambiguity.

A concept's optional `condition` is a typed Filter, for example `{"field":"customers.status","operator":"=","value":"active"}`. The planner adds the condition when the concept is used. Definitions expressed as Python strings are intentionally unsupported. Catalog fields `units`, `time_semantics`, `aggregation`, and `source_metadata` preserve business metadata but do not execute arbitrary conversions or formulas. Specify metric aggregation explicitly in intent.

Catalog mappings are visible in compiled provenance. Confidence is evidence of deterministic name grounding, not language understanding probability. Review the chosen monetary field, aggregation, currency and calendar policy for business-critical queries.
