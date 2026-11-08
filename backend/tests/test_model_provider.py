from app.model_provider import ModelResponse
from app.providers.fake import FakeModelProvider


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
