# v0.2 Week 1 Day 1：模型 Provider 抽象

## 已完成

- 增加同步 `ModelProvider` 协议：`generate(prompt, tools=None)`。
- 增加统一 `ModelResponse`，包含文本、工具调用、provider、model、耗时、token 用量和状态。
- 增加无网络的 `FakeModelProvider`，作为默认确定性测试替身。
- 工具定义只作为数据透传，FakeModel 不执行工具。

## 验证

```text
python -m pytest tests/test_model_provider.py -q
2 passed
```

Day 1 未接入真实 API、API Key 或外部依赖；这些属于后续 Day 2 任务。
