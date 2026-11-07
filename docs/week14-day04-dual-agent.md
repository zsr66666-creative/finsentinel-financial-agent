# 第十四周 Day 4：双 Agent 复核适配器

运行器：`experiments/week14/run_dual_agent.py`
结果：`data/evals/retrieval-run-week14-dual-agent.json`

## 结果

- 执行题数：56；冻结可评分题：59；
- 可比题数：0；命中：0；
- p50：16.25 ms；p95：17.75 ms；
- 超时：0；成本：0。

## 结论边界

当前 synthetic fixture evidence ID 与真实黄金问题 evidence ID 没有一一映射，因此所有题目都被标记为 `not_comparable`，没有伪造双 Agent 命中率。该运行器只验证分析阶段和独立证据复核阶段的状态分离、耗时记录和不可比性处理，不代表真实 LLM 双 Agent 质量。

要获得有效对照结果，下一步必须建立同一语料快照下的统一 evidence ID 映射，或只选取双方共享的 approved fixture 题集重新冻结分母。
