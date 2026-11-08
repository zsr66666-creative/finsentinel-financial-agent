from app.model_provider import ModelResponse
from app.providers.fake import FakeModelProvider
from app.providers.openai_compatible import ModelProviderError, OpenAICompatibleProvider
import httpx


def test_model_response_contract_has_runtime_metadata():
    response = ModelResponse(
        text="ok",
        provider="test",
        model="test-v1",
        latency_ms=1.2,
        token_usage={"input": 1, "output": 1},
    )
    assert response.text == "ok"
    assert response.tool_calls == []
    assert response.status == "success"


def test_fake_provider_is_deterministic_and_does_not_execute_tools():
    provider = FakeModelProvider()
    tools = [{"name": "calc_growth", "description": "calculate growth"}]
    first = provider.generate("分析现金流", tools=tools)
    second = provider.generate("分析现金流", tools=tools)
    assert first.text == second.text
    assert first.provider == "fake"
    assert first.model == "deterministic-demo-v1"
    assert first.tool_calls == []
    assert first.token_usage == {"input": 0, "output": 0}
    assert first.status == "success"


def test_real_provider_requires_api_key():
    try:
        OpenAICompatibleProvider(api_key="", model="m", base_url="https://example.test/v1")
    except ModelProviderError as exc:
        assert "MODEL_API_KEY" in str(exc)
    else:
        raise AssertionError("missing API key must fail")


class _FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def post(self, *args, **kwargs):
        self.calls += 1
        return next(self.responses)


def test_real_provider_retries_429_then_succeeds():
    failed = httpx.Response(429, request=httpx.Request("POST", "https://example.test"))
    ok = httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}, request=httpx.Request("POST", "https://example.test"))
    client = _FakeClient([failed, ok])
    result = OpenAICompatibleProvider(api_key="secret", model="m", base_url="https://example.test/v1", retry_backoff_seconds=0, client=client).generate("hi")
    assert result.text == "ok" and client.calls == 2
