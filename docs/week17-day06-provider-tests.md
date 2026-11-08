# v0.2 Week 1 Day 6：Provider 集成测试

## 覆盖范围

- 429 后重试并成功；
- 5xx 重试至上限后安全失败；
- 4xx 配置错误不重试；
- 空 choices 响应不会崩溃或执行工具；
- 测试使用假的 HTTP client，不调用真实外部 API。

## 验收

```text
python -m pytest -q
```

真实 Provider 仍需在配置 API Key 的独立环境中手动评测，测试不会伪造真实模型质量。
