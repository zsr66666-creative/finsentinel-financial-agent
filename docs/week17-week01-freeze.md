# v0.2 Week 1 冻结报告：真实 LLM Provider 基础

## 本周完成

1. 建立同步 `ModelProvider` / `ModelResponse` 接口。
2. 保留无网络的 `FakeModelProvider` 作为默认测试替身。
3. 增加 OpenAI-compatible `/chat/completions` Provider。
4. 从环境变量读取 provider、model、API Key、Base URL 和超时。
5. 增加超时、429、5xx 重试和指数退避。
6. 对 4xx、非法响应和重试耗尽返回安全错误。
7. 将 Provider 接入分析运行并记录 provider、model、耗时、token 用量、重试次数和错误。
8. 补充假的 HTTP client 集成测试，不调用真实外部 API。

## 验证结果

```text
后端全量测试：全部通过
```

覆盖内容包括 Provider 契约、环境配置、分析工作流接入、429/5xx/4xx、响应解析和审计字段。

## 明确限制

- 尚未使用真实 API Key 做线上模型质量评测。
- 尚未比较真实 LLM 与确定性工具的质量、成本和延迟。
- 默认配置仍为 `MODEL_PROVIDER=fake`，确保离线测试可复现。
- Provider 不执行工具；工具白名单仍由后端工作流控制。

## 下一周入口

第 2 周使用冻结的 Provider 接口，建立真实 LLM 单 Agent、双 Agent 和确定性工具的同题集对照实验，必须记录命中数/总题数、p50/p95 延迟、失败率和 API 成本。
