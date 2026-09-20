import json

import httpx
import pytest

from nlquery.core.models import QueryIntent
from nlquery.exceptions import ConfigurationError, IntentError
from nlquery.llm.providers import (
    AnthropicProvider,
    OllamaProvider,
    OpenAIProvider,
    provider_from_string,
)

MESSAGES = [{"role": "system", "content": "Interpret"}, {"role": "user", "content": "Show items"}]


def test_openai_real_sdk_transport(monkeypatch):
    openai = pytest.importorskip("openai")
    constructor = openai.OpenAI
    calls = []

    def handler(request):
        data = json.loads(request.content)
        calls.append(data)
        assert data["text"]["format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 0,
                "status": "completed",
                "model": "test",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": QueryIntent(sources=["items"]).model_dump_json(),
                                "annotations": [],
                            }
                        ],
                    }
                ],
                "parallel_tool_calls": False,
                "tool_choice": "auto",
                "tools": [],
            },
        )

    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda **kwargs: constructor(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
    )
    assert OpenAIProvider("test", api_key="synthetic-credential").structured_generate(
        MESSAGES, QueryIntent
    ).sources == ["items"]
    assert len(calls) == 1


def test_anthropic_real_sdk_transport(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    constructor = anthropic.Anthropic

    def handler(request):
        data = json.loads(request.content)
        assert data["tool_choice"]["name"] == "query_intent"
        return httpx.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "test",
                "stop_reason": "tool_use",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_test",
                        "name": "query_intent",
                        "input": {"sources": ["items"]},
                    }
                ],
            },
        )

    monkeypatch.setattr(
        anthropic,
        "Anthropic",
        lambda **kwargs: constructor(
            **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler))
        ),
    )
    assert AnthropicProvider("test", api_key="synthetic-credential").structured_generate(
        MESSAGES, QueryIntent
    ).sources == ["items"]


def test_ollama_transport(monkeypatch):
    constructor = httpx.Client

    def handler(request):
        data = json.loads(request.content)
        assert data["stream"] is False
        assert data["format"]["additionalProperties"] is False
        assert json.dumps(data["format"]) in data["messages"][0]["content"]
        assert data["messages"][-1] == MESSAGES[-1]
        return httpx.Response(200, json={"message": {"content": '{"sources":["items"]}'}})

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: constructor(**kwargs, transport=httpx.MockTransport(handler)),
    )
    assert OllamaProvider("test").structured_generate(MESSAGES, QueryIntent).sources == ["items"]


@pytest.mark.parametrize("value", ["bad", "unknown:x", ":", "ollama:"])
def test_bad_provider(value):
    with pytest.raises(ConfigurationError):
        provider_from_string(value)


@pytest.mark.parametrize("name", ["openai", "anthropic", "ollama"])
def test_provider_selection(name):
    assert provider_from_string(name + ":test").model == "test"


def test_safe_error(monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("token=do-not-disclose")

    monkeypatch.setattr(httpx, "Client", broken)
    with pytest.raises(IntentError) as exc:
        OllamaProvider("test").structured_generate(MESSAGES, QueryIntent)
    assert "do-not-disclose" not in str(exc.value)
