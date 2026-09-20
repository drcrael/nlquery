"""Lazy SDK adapters with bounded network requests and no raw error propagation."""

import json
import os
from typing import Any, Literal, cast

from nlquery.core.models import QueryIntent
from nlquery.exceptions import ConfigurationError, IntentError
from nlquery.llm.base import LLMProvider


class OpenAIProvider:
    def __init__(self, model: str, api_key: str | None = None, timeout: float = 60) -> None:
        self.model = model
        self._key = api_key or os.getenv("OPENAI_API_KEY")
        self.timeout = timeout

    def secret_values(self) -> list[str]:
        return [self._key] if self._key else []

    def __repr__(self) -> str:
        return "OpenAIProvider(credentials=<redacted>)"

    def structured_generate(
        self, messages: list[dict[str, str]], response_model: type[QueryIntent], **kwargs: Any
    ) -> QueryIntent:
        try:
            from openai import OpenAI
            from openai.types.responses import ResponseInputParam
        except ImportError:
            raise ConfigurationError("Install nlquery[openai]") from None
        try:
            with OpenAI(api_key=self._key, timeout=self.timeout, max_retries=0) as client:
                typed_messages: ResponseInputParam = [
                    {
                        "role": cast(
                            Literal["user", "assistant", "system", "developer"], m["role"]
                        ),
                        "content": m["content"],
                    }
                    for m in messages
                ]
                result = client.responses.parse(
                    model=self.model, input=typed_messages, text_format=response_model
                )
                if result.output_parsed is None:
                    raise IntentError("Model refused or returned no structured intent")
                return response_model.model_validate(result.output_parsed.model_dump())
        except Exception:
            raise IntentError("OpenAI structured generation failed") from None


class AnthropicProvider:
    def __init__(self, model: str, api_key: str | None = None, timeout: float = 60) -> None:
        self.model = model
        self._key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.timeout = timeout

    def secret_values(self) -> list[str]:
        return [self._key] if self._key else []

    def __repr__(self) -> str:
        return "AnthropicProvider(credentials=<redacted>)"

    def structured_generate(
        self, messages: list[dict[str, str]], response_model: type[QueryIntent], **kwargs: Any
    ) -> QueryIntent:
        try:
            from anthropic import Anthropic
            from anthropic.types import MessageParam, ToolParam
        except ImportError:
            raise ConfigurationError("Install nlquery[anthropic]") from None
        try:
            with Anthropic(api_key=self._key, timeout=self.timeout, max_retries=0) as client:
                typed_messages: list[MessageParam] = [
                    {"role": cast(Literal["user", "assistant"], m["role"]), "content": m["content"]}
                    for m in messages
                    if m["role"] != "system"
                ]
                tool: ToolParam = {
                    "name": "query_intent",
                    "description": "Return semantic intent",
                    "input_schema": response_model.model_json_schema(),
                }
                response = client.messages.create(
                    model=self.model,
                    max_tokens=8192,
                    system="\n".join(m["content"] for m in messages if m["role"] == "system"),
                    messages=typed_messages,
                    tools=[tool],
                    tool_choice={"type": "tool", "name": "query_intent"},
                )
                for block in response.content:
                    if block.type == "tool_use" and block.name == "query_intent":
                        return response_model.model_validate(block.input)
                raise IntentError("No structured tool result")
        except Exception:
            raise IntentError("Anthropic structured generation failed") from None


class OllamaProvider:
    def __init__(
        self, model: str, base_url: str = "http://localhost:11434", timeout: float = 120
    ) -> None:
        from urllib.parse import urlsplit

        parsed = urlsplit(base_url)
        if parsed.username or parsed.password or parsed.scheme not in {"http", "https"}:
            raise ConfigurationError(
                "Provider endpoint must be HTTP(S) without embedded credentials"
            )
        self.model = model
        self._url = base_url.rstrip("/")
        self.timeout = timeout

    def __repr__(self) -> str:
        return "OllamaProvider(endpoint=<configured>)"

    def structured_generate(
        self, messages: list[dict[str, str]], response_model: type[QueryIntent], **kwargs: Any
    ) -> QueryIntent:
        try:
            import httpx
        except ImportError:
            raise ConfigurationError("Install nlquery[ollama]") from None
        try:
            with httpx.Client(
                timeout=self.timeout, follow_redirects=False, trust_env=False
            ) as client:
                schema = response_model.model_json_schema()
                instructions = (
                    "Required response JSON schema: "
                    + json.dumps(schema)
                    + "\nUse the schema to interpret each output property. "
                    "Keep unused fields at their defaults. backend_hints is reserved; leave it empty."
                )
                grounded = [dict(message) for message in messages]
                if grounded and grounded[0]["role"] == "system":
                    grounded[0]["content"] += "\n" + instructions
                else:
                    grounded.insert(0, {"role": "system", "content": instructions})
                response = client.post(
                    self._url + "/api/chat",
                    json={
                        "model": self.model,
                        "messages": grounded,
                        "format": schema,
                        "stream": False,
                        "options": {"temperature": 0, "num_ctx": 16384},
                    },
                )
                response.raise_for_status()
                return response_model.model_validate_json(response.json()["message"]["content"])
        except Exception:
            raise IntentError("Ollama structured generation failed") from None


def provider_from_string(value: str) -> LLMProvider:
    name, sep, model = value.partition(":")
    if not sep or not model:
        raise ConfigurationError("Provider specification must be provider:model")
    if name == "openai":
        return OpenAIProvider(model, os.getenv("OPENAI_API_KEY"))
    if name == "anthropic":
        return AnthropicProvider(model, os.getenv("ANTHROPIC_API_KEY"))
    if name == "ollama":
        return OllamaProvider(model)
    raise ConfigurationError("Unknown LLM provider")
