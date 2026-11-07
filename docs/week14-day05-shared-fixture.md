# 第十四周 Day 5：共享可比题集

已冻结 `data/evals/week14-shared-fixture.jsonl` 作为单 Agent/双 Agent 对照专用题集。

- 题数：40 条；
- 来源：系统当前已批准的 synthetic fixture metrics；
- 每条题目都保存真实可查询的 fixture `gold_evidence_ids`；
- 数据版本：`synthetic-demo-v1`；
- 题目划分：全部 `development`，不与真实 PDF 黄金测试集混用；
- 该题集只用于验证 Agent 流程、证据引用和延迟差异，不代表真实财报质量。

从现在开始，单 Agent 与双 Agent 必须使用这份文件，分母固定为 40。
