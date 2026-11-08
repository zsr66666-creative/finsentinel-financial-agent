# Day 1 Model Provider Design

## Goal

Introduce a synchronous model provider boundary without changing the existing deterministic workflow or making network calls.

## Interface

`ModelProvider.generate(prompt: str, tools: list[dict] | None = None) -> ModelResponse`

`ModelResponse` contains `text`, `tool_calls`, `provider`, `model`, `latency_ms`, `token_usage`, and `status`.

## Components

- `model_provider.py`: protocol and response dataclass.
- `providers/fake.py`: deterministic FakeModel implementation.
- `tests/test_model_provider.py`: contract tests.

## Constraints

- FakeModel remains the default and performs no network access.
- Tool definitions are passed through as data only; the provider cannot execute tools.
- No API keys or provider configuration are added in Day 1.
