# 第十四周 Day 5：可比 Agent 实验冻结

## 解决方案

真实 PDF 黄金集与 synthetic fixture 的 evidence ID 不同，不能直接比较。现已冻结一份双方共享的 40 条 approved fixture 题集：

`data/evals/week14-shared-fixture.jsonl`

每题都从当前 API 的 `financial_metrics.source_ids` 生成，证据 ID 可被单 Agent 和双 Agent 同时查询。该题集全部为 `development`，与真实 PDF 测试集隔离。

## 重新运行结果

| 条件 | 命中数 / 总数 | p50 | p95 | 超时 |
|---|---:|---:|---:|---:|
| 单 Agent 确定性适配器 | 40 / 40 | 18.07 ms | 20.10 ms | 0 / 40 |
| 双 Agent 确定性复核适配器 | 40 / 40 | 16.54 ms | 19.50 ms | 0 / 40 |

两组的证据命中、引用覆盖和工具成功率均为 40 / 40。成本为 0，因为没有外部模型调用。

## 边界

这证明的是同一 synthetic fixture 下两个流程的可比性和审计记录，不代表真实 PDF 或 LLM 泛化效果。真实黄金集仍需单独报告，不能与这 40 条合并。
