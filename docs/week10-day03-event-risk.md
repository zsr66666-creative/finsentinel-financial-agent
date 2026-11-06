# 第十周 Day 3：公告事件与风险证据

## 本次变更

- 新增 `data/evals/event-evidence-week10.jsonl`，包含 7 条可追溯证据记录。
- 证据覆盖：减值、诉讼（否定披露）、重大客户/客户集中风险、关联交易、回购、担保。
- 新增 6 条黄金问题，全部进入 `development`。
- 每条问题均引用人工核验的 `document_id`、页码和原文 span。

## 语义边界

- 领益智造诉讼证据是“无涉及诉讼的对外担保”的否定披露，不能回答为公司存在诉讼。
- 蓝思科技材料披露的是客户集中风险及其潜在影响，不能虚构具体客户名称或客户金额。
- 担保证据同时保留担保金额和无逾期/无涉诉担保状态，不能把担保额度直接解释为已发生损失。

## 验证

- 事件证据 JSONL 可解析。
- 7 条证据均为 `human_reviewed`。
- 新增 6 条问题全部为 `development`，未修改原有 `test` 集。
- 黄金问题总数由 68 条增至 74 条。

文件：`data/evals/event-evidence-week10.jsonl`、`data/evals/golden_questions.jsonl`。
