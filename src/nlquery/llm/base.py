"""Provider-neutral structured interpretation contract."""

from typing import Any, Protocol

from nlquery.core.models import QueryIntent


class LLMProvider(Protocol):
    def structured_generate(
        self, messages: list[dict[str, str]], response_model: type[QueryIntent], **kwargs: Any
    ) -> QueryIntent:
        """Return a validated structured intent, never backend syntax."""
        ...
