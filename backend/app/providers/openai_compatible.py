from time import perf_counter
from time import sleep
from typing import Any
import httpx
from ..model_provider import ModelResponse


class ModelProviderError(RuntimeError):
    """Safe provider failure without secret material."""


class OpenAICompatibleProvider:
    provider = "openai-compatible"

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_seconds: float = 30.0, max_retries: int = 2, retry_backoff_seconds: float = 0.25, client: httpx.Client | None = None):
        if not api_key:
            raise ModelProviderError("MODEL_API_KEY is required for a real model provider")
        self.api_key, self.model, self.base_url = api_key, model, base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def generate(self, prompt: str, tools: list[dict[str, Any]] | None = None) -> ModelResponse:
        started = perf_counter()
        payload: dict[str, Any] = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}
        if tools:
            payload["tools"] = [{"type": "function", "function": tool} for tool in tools]
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.post(f"{self.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=payload)
                response.raise_for_status()
                body = response.json(); choice = (body.get("choices") or [{}])[0]; message = choice.get("message") or {}; usage = body.get("usage") or {}
                return ModelResponse(text=message.get("content") or "", provider=self.provider, model=self.model, latency_ms=round((perf_counter() - started) * 1000, 3), token_usage={"input": int(usage.get("prompt_tokens", 0)), "output": int(usage.get("completion_tokens", 0))}, tool_calls=message.get("tool_calls") or [], retry_count=attempt)
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    sleep(self.retry_backoff_seconds * (2 ** attempt)); continue
                raise ModelProviderError("model request timed out after retries") from exc
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 429 or status >= 500:
                    if attempt < self.max_retries:
                        sleep(self.retry_backoff_seconds * (2 ** attempt)); continue
                    raise ModelProviderError(f"model provider returned HTTP {status} after retries") from exc
                raise ModelProviderError(f"model provider returned HTTP {status}") from exc
            except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError) as exc:
                raise ModelProviderError("model provider response could not be parsed") from exc
