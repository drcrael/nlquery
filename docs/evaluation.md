# Evaluation and evidence

`tests/golden/cases.json` contains 50 version-controlled natural-language requests across ecommerce, finance, inventory, operations, IoT, software, support and project-management examples. It includes expected intents, backend and acceptance/rejection outcomes. `test_corpus.py` replays these through an explicit mock provider and compares canonical plans across compatible compilers.

**Mock replay is not model inference.** It tests structured-output validation and deterministic software. Rejection fixtures test ambiguity, unknown schema, unsupported operations, injection-like values and result bounds.

For actual provider evaluation:

```bash
python scripts/evaluate.py --provider ollama:qwen3 --output evaluation.json
# Paid providers require your own credentials and incur provider charges:
python scripts/evaluate.py --provider openai:YOUR_MODEL --output evaluation.json
```

Metrics include source, fields, filters/boolean structure, aggregations/groups, relationships, relative times/windows, ambiguity and exact intent match. Defaults and ordering affect exact match. These are explicit comparisons, not a claim of a fully general semantic equivalence solver.

The separate `Live local model acceptance` workflow runs Qwen2.5 7B through Ollama on two paraphrases, records raw intent metrics, requires canonical-plan agreement, and executes the actual returned plans against SQLite. It saves the actual intents, metric outcomes and execution comparisons as an artifact, including on failure. No fixture replaces inference. Failures remain failures; do not loosen the validator to accommodate a model. See VALIDATION.md for the retained failed 3B and initial 7B attempts and the actual latest results. The cases are development acceptance cases used during prompt refinement, not a held-out benchmark.

Interpretation of benchmark outputs should distinguish exact match, grounding success, compilation success and correct returned data. One successful smoke test does not establish broad accuracy or production suitability.
