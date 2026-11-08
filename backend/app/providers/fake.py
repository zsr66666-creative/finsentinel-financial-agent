from time import perf_counter
from typing import Any

from ..model_provider import ModelResponse


class FakeModelProvider:
    provider = "fake"
    model = "deterministic-demo-v1"

    def generate(self, prompt: str, tools: list[dict[str, Any]] | None = None) -> ModelResponse:
        started = perf_counter()
        text = "这是确定性演示模型输出：请结合原始证据和人工复核后使用。"
        return ModelResponse(
            text=text,
            provider=self.provider,
            model=self.model,
            latency_ms=round((perf_counter() - started) * 1000, 3),
            token_usage={"input": 0, "output": 0},
            tool_calls=[],
        )
