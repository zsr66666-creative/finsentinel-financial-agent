# v0.2 Week 1 Day 2：真实 Provider 配置

## 已完成

- 增加 `ModelSettings.from_env()`，统一读取 provider、model、API Key、Base URL 和超时。
- 增加 OpenAI-compatible `/chat/completions` Provider。
- API Key 缺失、超时、HTTP 错误和响应解析错误会转为不泄露密钥的 `ModelProviderError`。
- 默认仍为 `MODEL_PROVIDER=fake`，不会主动发起外部请求。

## 配置示例

```env
MODEL_PROVIDER=openai-compatible
MODEL_NAME=your-model
MODEL_API_KEY=your-secret
MODEL_BASE_URL=https://api.openai.com/v1
MODEL_TIMEOUT_SECONDS=30
```

Day 2 尚未把真实 Provider 接入分析工作流，也没有发起真实 API 调用。
