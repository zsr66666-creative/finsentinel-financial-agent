# 第十周检索评测报告（人工核验后重跑）

- 运行时间（UTC）：`2026-11-06T05:25:09Z`
- 代码版本：`0850105bf97317b56753ec97191bad17aef334fc`
- 语料版本：`week10-reviewed`
- 黄金问题：74 条；可评分题：59 条
- 检索：BM25 + 查询扩展；向量嵌入未配置；Top-K 5/10

## 总体结果

| 指标 | 命中数 / 总题数 | 可评分题 | 结果 |
|---|---:|---:|---:|
| Recall@5 | 47 / 74 | 59 | 0.7966 |
| Recall@10 | 50 / 74 | 59 | 0.8475 |

## 数据集划分（Recall@5）

| 划分 | 命中数 / 总题数 | 可评分题 | Recall@5 |
|---|---:|---:|---:|
| development | 44 / 62 | 55 | 0.8000 |
| test | 3 / 12 | 4 | 0.7500 |

## 公司拆分（Recall@5）

| 公司 | 命中数 / 总题数 | 可评分题 | Recall@5 |
|---|---:|---:|---:|
| `cn-002241` | 7 / 7 | 7 | 1.0000 |
| `cn-002475` | 22 / 41 | 26 | 0.8462 |
| `cn-002600` | 5 / 9 | 9 | 0.5556 |
| `cn-300115` | 6 / 8 | 8 | 0.7500 |
| `cn-300433` | 7 / 9 | 9 | 0.7778 |

## 题型拆分（Recall@5）

| 题型 | 命中数 / 总题数 | 可评分题 | Recall@5 |
|---|---:|---:|---:|
| `announcement_event` | 0 / 3 | 3 | 0.0000 |
| `calculation` | 5 / 6 | 6 | 0.8333 |
| `correct_refusal` | 2 / 17 | 3 | 0.6667 |
| `evidence_location` | 11 / 11 | 11 | 1.0000 |
| `evidence_support` | 0 / 1 | 0 | N/A |
| `fact_lookup` | 24 / 28 | 28 | 0.8571 |
| `risk_explanation` | 0 / 2 | 2 | 0.0000 |
| `rule` | 1 / 1 | 1 | 1.0000 |
| `scope` | 4 / 5 | 5 | 0.8000 |

## 漏检

- Recall@5：12 条；Recall@10：9 条。

| case_id | 公司 | 题型 | split | 黄金证据 |
|---|---|---|---|---|
| `case-015` | `cn-002475` | `fact_lookup` | `development` | 002475-2025FY-p43-s9 |
| `case-017` | `cn-002475` | `scope` | `development` | 002475-2025FY-p8-s16 |
| `case-021` | `cn-002475` | `calculation` | `development` | 002475-2025FY-p8-s20 |
| `case-048` | `cn-300115` | `fact_lookup` | `test` | 300115-2024FY-p0-s0 |
| `case-055` | `cn-002600` | `fact_lookup` | `development` | 002600-2025FY-p2-s7 |
| `case-062` | `cn-300115` | `fact_lookup` | `development` | 300115-2024FY-p0-s0 |
| `case-069` | `cn-300433` | `announcement_event` | `development` | week10-event-impairment-001 |
| `case-070` | `cn-002600` | `correct_refusal` | `development` | week10-event-litigation-001 |
| `case-071` | `cn-300433` | `risk_explanation` | `development` | week10-risk-customer-concentration-001 |
| `case-072` | `cn-002475` | `announcement_event` | `development` | week10-event-related-party-001 |
| `case-073` | `cn-002600` | `announcement_event` | `development` | week10-event-buyback-001 |
| `case-074` | `cn-002600` | `risk_explanation` | `development` | week10-event-guarantee-001 |

## 说明

本次重跑使用人工核验后的 59 条有证据题；15 条正确拒答题没有黄金证据，不进入 Recall 分母。与修改前的 34/74、35/74 不应直接作严格回归比较，因为题目证据状态发生了变化。

原始结果：`data/evals/retrieval-run-week10.json`。
