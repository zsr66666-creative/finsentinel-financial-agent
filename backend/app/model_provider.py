from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelResponse:
    text: str
    provider: str
    model: str
    latency_ms: float
    token_usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    status: str = "success"
    retry_count: int = 0


class ModelProvider(Protocol):
    provider: str
    model: str

    def generate(self, prompt: str, tools: list[dict[str, Any]] | None = None) -> ModelResponse:
        """Generate a response; tool definitions are data and are never executed here."""
        ...
