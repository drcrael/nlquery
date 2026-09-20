"""Replaceable bounded lexical schema retrieval; metadata is always untrusted."""

import re
from typing import Protocol

from nlquery.core.models import DiscoveryConfig, SchemaModel, SemanticCatalog
from nlquery.exceptions import PlanningError


class SchemaRetriever(Protocol):
    def retrieve(
        self, question: str, schema: SchemaModel, catalog: SemanticCatalog, config: DiscoveryConfig
    ) -> SchemaModel: ...


class LexicalRetriever:
    def retrieve(
        self, question: str, schema: SchemaModel, catalog: SemanticCatalog, config: DiscoveryConfig
    ) -> SchemaModel:
        tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
        relevant: set[str] = set()
        for name, c in catalog.concepts.items():
            if any(term.lower() in question.lower() for term in [name, *c.aliases]):
                relevant.update(v.split(".")[0] for v in c.candidates)

        def score(index: int) -> tuple[int, int]:
            s = schema.sources[index]
            words = set(
                re.findall(
                    r"[a-z0-9]+",
                    " ".join([s.name, s.description, *[f.name for f in s.fields]]).lower(),
                )
            )
            return (len(tokens & words) + 10 * (s.name in relevant), -index)

        indices = sorted(range(len(schema.sources)), key=score, reverse=True)[
            : config.max_context_sources
        ]
        selected = [schema.sources[i] for i in indices]
        names = {s.name for s in selected}
        result = SchemaModel(
            backend=schema.backend,
            sources=selected,
            relationships=[
                e for e in schema.relationships if e.source in names and e.target in names
            ],
        )
        if len(result.model_dump_json()) > config.max_context_chars:
            raise PlanningError("Retrieved schema exceeds context budget; narrow the schema")
        return result
