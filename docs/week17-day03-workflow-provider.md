# v0.2 Week 1 Day 3：Provider 接入分析工作流

## 已完成

- 分析运行根据 `MODEL_PROVIDER` 选择 FakeModel 或 OpenAI-compatible Provider。
- 运行记录保存 `model_provider`、`model_version`、`model_latency_ms`、`token_usage` 和 `model_error`。
- Provider 错误会将运行标记为 `needs_review`，不会生成未经证据校验的新结论。
- 原有 Planner、DataQuality、Retriever、QuantAnalyst、EvidenceVerifier、ReportComposer 轨迹保持兼容。

## 验证

```text
python -m pytest -q
全部通过
```

默认测试使用 FakeModel，不发起外部网络请求；真实 Provider 需要在后续环境中显式配置并单独评测。
