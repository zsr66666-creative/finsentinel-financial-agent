import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSettings:
    provider: str = "fake"
    model: str = "deterministic-demo-v1"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "ModelSettings":
        return cls(provider=os.getenv("MODEL_PROVIDER", "fake").strip().lower(), model=os.getenv("MODEL_NAME", "deterministic-demo-v1").strip(), api_key=os.getenv("MODEL_API_KEY", os.getenv("OPENAI_API_KEY", "")), base_url=os.getenv("MODEL_BASE_URL", "https://api.openai.com/v1").rstrip("/"), timeout_seconds=float(os.getenv("MODEL_TIMEOUT_SECONDS", "30")))
