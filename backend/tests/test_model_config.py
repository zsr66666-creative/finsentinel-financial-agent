from app.model_config import ModelSettings


def test_model_settings_default_to_fake(monkeypatch):
    monkeypatch.delenv("MODEL_PROVIDER", raising=False); monkeypatch.delenv("MODEL_API_KEY", raising=False)
    settings = ModelSettings.from_env()
    assert settings.provider == "fake" and settings.model == "deterministic-demo-v1"


def test_model_settings_read_compatible_provider(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai-compatible"); monkeypatch.setenv("MODEL_NAME", "test-model"); monkeypatch.setenv("MODEL_API_KEY", "secret"); monkeypatch.setenv("MODEL_BASE_URL", "https://example.test/v1/")
    settings = ModelSettings.from_env()
    assert settings.provider == "openai-compatible" and settings.api_key == "secret" and settings.base_url == "https://example.test/v1"
