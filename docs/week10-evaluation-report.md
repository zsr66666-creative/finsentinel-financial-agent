# 第十周检索评测报告

## 运行元数据

| 字段 | 值 |
|---|---|
| 运行时间（UTC） | `2026-11-06T01:27:08Z` |
| 代码版本 | `0867290936e646734c81a869b32e2b198ed3e030` |
| 语料版本 | `week10-multi-company-v3` |
| 问题集 | `data/evals/golden_questions.jsonl` |
| 总题数 | 74 |
| 检索模式 | `query_expansion` |
| Top-K | 5 和 10 |
| 向量嵌入 | 未配置（BM25 + 查询扩展） |

## 总体结果

| 指标 | 命中数 / 总题数 | 可评分题 | 结果 |
|---|---:|---:|---:|
| Recall@5 | 34 / 74 | 43 | 0.7907 |
| Recall@10 | 35 / 74 | 43 | 0.8140 |

## 按数据集划分（Recall@5）

| 划分 | 命中数 / 总题数 | 可评分题 | Recall@5 |
|---|---:|---:|---:|
| development | 31 / 62 | 39 | 0.7949 |
| test | 3 / 12 | 4 | 0.7500 |

## 按公司（Recall@5）

| 公司 | 命中数 / 总题数 | 可评分题 | Recall@5 |
|---|---:|---:|---:|
| `cn-002241` | 7 / 7 | 7 | 1.0000 |
| `cn-002475` | 9 / 41 | 10 | 0.9000 |
| `cn-002600` | 5 / 9 | 9 | 0.5556 |
| `cn-300115` | 6 / 8 | 8 | 0.7500 |
| `cn-300433` | 7 / 9 | 9 | 0.7778 |

## 按题型（Recall@5）

| 题型 | 命中数 / 总题数 | 可评分题 | Recall@5 |
|---|---:|---:|---:|
| `announcement_event` | 0 / 7 | 3 | 0.0000 |
| `calculation` | 2 / 9 | 2 | 1.0000 |
| `correct_refusal` | 2 / 3 | 3 | 0.6667 |
| `evidence_location` | 6 / 11 | 6 | 1.0000 |
| `evidence_support` | 0 / 1 | 0 | N/A |
| `fact_lookup` | 20 / 30 | 23 | 0.8696 |
| `peer_comparison` | 0 / 3 | 0 | N/A |
| `risk_explanation` | 0 / 6 | 2 | 0.0000 |
| `rule` | 1 / 1 | 1 | 1.0000 |
| `scope` | 3 / 3 | 3 | 1.0000 |

## 漏检清单

- Recall@5 漏检：9 条可评分题。
- Recall@10 漏检：{len(miss10)} 条可评分题。

| case_id | 公司 | 题型 | split | 黄金证据 |
|---|---|---|---|---|
| `case-048` | `cn-300115` | `fact_lookup` | `test` | `300115-2024FY-p0-s0 |
| `case-055` | `cn-002600` | `fact_lookup` | `development` | `002600-2025FY-p2-s7 |
| `case-062` | `cn-300115` | `fact_lookup` | `development` | `300115-2024FY-p0-s0 |
| `case-069` | `cn-300433` | `announcement_event` | `development` | `week10-event-impairment-001 |
| `case-070` | `cn-002600` | `correct_refusal` | `development` | `week10-event-litigation-001 |
| `case-071` | `cn-300433` | `risk_explanation` | `development` | `week10-risk-customer-concentration-001 |
| `case-072` | `cn-002475` | `announcement_event` | `development` | `week10-event-related-party-001 |
| `case-073` | `cn-002600` | `announcement_event` | `development` | `week10-event-buyback-001 |
| `case-074` | `cn-002600` | `risk_explanation` | `development` | `week10-event-guarantee-001 |

## 与第九周基线比较

- 第九周：9 / 48，Recall@5 = 0.5294。
- 第十周当前最佳：34 / 74，Recall@5 = 0.7907。
- 第十周 Recall@10：35 / 74，Recall@10 = 0.8140。
- 第十周问题数增加 26 条，不能只比较百分比；命中数和可评分题分母均已列出。

## 限制

- 当前最佳策略为 BM25 + 查询扩展，向量嵌入未配置。
- 新增黄金问题全部为 development；test 集保持原有题目。
- 命中判定支持精确 evidence ID 或同一文档页规范化匹配，避免 span/chunk ID 版本差异造成假漏检。

原始明细：`data/evals/retrieval-run-week10.json`。
