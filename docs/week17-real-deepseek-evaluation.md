# Week 17 真实 DeepSeek 评测记录

## 运行信息

- Provider：DeepSeek `deepseek-chat`
- 数据集：`data/evals/golden_questions.jsonl`
- 划分：development，10 条
- 语料版本：`week10-multi-company-v3`
- 评测结果文件：`data/evals/week17-llm-comparison.json`
- 证据上下文：`data/evals/week17-evidence-context.json`
- 运行模式：真实 provider；API Key 仅通过进程环境变量提供

## 结果

| 条件 | 证据命中数 / 总题数 | 失败数 / 总请求数 | p50 延迟 | p95 延迟 | 成本 |
|---|---:|---:|---:|---:|---:|
| 单 Agent | 10 / 10 | 0 / 10 | 877.40 ms | 927.08 ms | 3.80653 USD |
| 双 Agent | 10 / 10 | 0 / 10 | 1502.05 ms | 1627.14 ms | 7.61541 USD |

## 人工核验边界

- 证据 ID 命中为 10 / 10，但这不自动等于答案正确率 10 / 10。
- `case-014` 的题目“2024 年末存货”和黄金答案 `69,327,010,925.99 元`口径不一致；该数实际对应归属于上市公司股东的净资产。该题在修正题目或黄金答案前不纳入正式答案准确率。
- 当前可确认前 9 条答案与证据均正确；`case-014` 暂不计入答案准确率，因此暂记答案正确 9 / 9 个有效题。
- 双 Agent 在本次结果中没有显示质量优势，延迟和成本约为单 Agent 的两倍；不能据此宣称双 Agent 更优。

## Week 3 状态

- Task 1：已完成并验证。
- Task 2：已完成 SQLite up/down/幂等测试。
- Task 3：未完成。PostgreSQL 启动接入、数据库失败健康检查和 API parity 尚未验收。
- 因此当前项目**不能宣称 PostgreSQL 生产可用**。

