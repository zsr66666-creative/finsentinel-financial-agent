# v0.2 Week 2 Day 3：统一对照输出

统一汇总文件：`data/evals/week17-comparison-summary.json`。

每个条件都使用统一字段：

- `hits` / `total` / `evaluated`；
- `failure_count` / `failure_rate`；
- `p50_latency_ms` / `p95_latency_ms`；
- `cost_usd`；
- provider、model、Prompt、语料和数据集版本。

当前输出标记为 `adapter_only`，不代表真实 LLM 质量。真实 LLM 运行必须使用同一格式并单独记录 API 成本。
