# v0.2 Week 1 Day 5：模型调用审计日志

## 已完成

分析运行记录现在保存：

- `model_provider`
- `model_version`
- `model_latency_ms`
- `model_retry_count`
- `token_usage`
- `model_error`

不保存 API Key、Authorization 请求头或完整敏感请求内容。重试次数来自 Provider 响应元数据；失败时记录安全错误文本。
