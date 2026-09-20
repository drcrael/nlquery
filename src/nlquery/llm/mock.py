"""Caller-supplied deterministic responses; this is not a language model."""

from collections.abc import Callable
from typing import Any

from nlquery.core.models import QueryIntent


class MockProvider:
    def __init__(
        self, response: QueryIntent | dict[str, Any] | Callable[[list[dict[str, str]]], Any]
    ) -> None:
        self._response = response
        self.calls = 0

    def structured_generate(
        self, messages: list[dict[str, str]], response_model: type[QueryIntent], **kwargs: Any
    ) -> QueryIntent:
        self.calls += 1
        value = self._response(messages) if callable(self._response) else self._response
        return response_model.model_validate(
            value.model_dump() if isinstance(value, QueryIntent) else value
        )
