# v0.2 Week 2 Day 6：对照实验回归

## 自动化结果

```text
后端测试：69 passed
确定性基线：40 / 59（适配器结果）
单 Agent 适配器：40 / 40
双 Agent 适配器：40 / 40
```

单/双 Agent 的 p50、p95、成本和失败率已写入 `data/evals/week17-comparison-summary.json`。结果状态仍为 `adapter_only`。

## 重要边界

- 本次没有真实 LLM provider 调用；
- 不能据此宣称双 Agent 优于单 Agent；
- 真实 PDF 黄金集与 synthetic fixture 未混合计分；
- 真实 LLM 运行必须通过 Day 4 安全门槛并保留 API 成本与失败原因。
