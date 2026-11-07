# 第十四周 Day 2：确定性工具基线

运行文件：`experiments/week14/run_deterministic_baseline.py`
结果文件：`data/evals/retrieval-run-week14-deterministic-baseline.json`

## 结果

- 冻结黄金问题：74 条；可评分题：59 条；
- 本次确定性 fixture 基线实际执行：40 条 approved case；
- 运行耗时：结果文件中的 `elapsed_ms`；
- 数值正确率、引用覆盖率和工具成功率按实际 40 条样本记录；
- 超时率：0 / 40；
- 成本：0（确定性工具，无模型调用）。

## 口径限制

这 40 条是系统内已批准的 synthetic fixture case，不等于第十四周冻结的 59 条真实黄金问题。因此本结果只作为确定性工具基线，不能直接与后续 Agent 的 59 题结果比较。Day 3 起需要使用同一可执行题集或明确报告不可评分题，避免改变分母。
