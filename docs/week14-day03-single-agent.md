# 第十四周 Day 3：单 Agent 基线

运行器：`experiments/week14/run_single_agent.py`
结果：`data/evals/retrieval-run-week14-single-agent.json`

## 实测结果

- 冻结问题总数：74；冻结可评分题：59；
- 本次可执行单 Agent 适配器样本：56 条；
- 证据命中：0 / 56；
- 引用覆盖：按接口 verification 记录为 31 / 56；
- 工具成功：44 / 56；
- p50：16.87 ms；p95：19.02 ms；
- 超时：0 / 56；成本：0。

## 解释

当前 API 的 synthetic fixture evidence ID 与冻结黄金问题中的真实 PDF evidence ID 不一致，因此不能把 0 / 56 解读成检索或 Agent 能力为零。该差异已记录为实验可比性缺口。当前没有外部 LLM provider，结果是单一确定性 workflow adapter，不是实测 LLM 单 Agent 结果。

Day 4 应先建立统一的 evidence ID 映射或缩小到双方都能执行的同一题集，再运行双 Agent 对照；不应直接用不同证据 ID 的结果比较 Agent 优劣。
