# 第十周 Day 4：检索策略对照实验

## 实验配置

| 版本 | 检索模式 | 语料版本 | 题数 | 可评分题 | 命中数 | Recall@5 |
|---|---|---|---:|---:|---:|---:|
| `retrieval-run-week10-bm25.json` | `bm25` | `week10-multi-company-v3` | 74 | 43 | 24 | 0.5581 |
| `retrieval-run-week10-query-expansion.json` | `query_expansion` | `week10-multi-company-v3` | 74 | 43 | 29 | 0.6744 |
| `retrieval-run-week10-chunk-merge.json` | `weighted` | `week10-multi-company-v3` | 74 | 43 | 29 | 0.6744 |

## 实验版本

- `retrieval-run-week10-bm25.json`：基础 BM25。
- `retrieval-run-week10-query-expansion.json`：BM25 + 财务指标、事件和口径同义词扩展。
- `retrieval-run-week10-chunk-merge.json`：查询扩展 + 页面 chunk 合并与证据类型加权。
- Top-K 固定为 5；向量嵌入未配置。
- 命中判定同时支持精确 evidence ID 和同一文档/页的规范化 page key，避免 `s` span 与 `m` merged chunk ID 不一致造成假漏检。

## 结论

查询扩展将命中数从 24 / 74 提升到 29 / 74，Recall@5 从 0.5581 提升到 0.6744。当前 chunk 合并/证据类型加权与查询扩展并列为 29 / 74、Recall@5 0.6744，暂未观察到额外提升。

## 分集结果

| 版本 | development 命中 / 总题数 | development Recall@5 | test 命中 / 总题数 | test Recall@5 |
|---|---:|---:|---:|---:|
| `retrieval-run-week10-bm25.json` | 22 / 62 | 0.5641 | 2 / 12 | 0.5000 |
| `retrieval-run-week10-query-expansion.json` | 26 / 62 | 0.6667 | 3 / 12 | 0.7500 |
| `retrieval-run-week10-chunk-merge.json` | 26 / 62 | 0.6667 | 3 / 12 | 0.7500 |

## 仍未命中的可评分题

查询扩展版本仍有 14 条可评分漏检：

| case_id | 公司 | 题型 | split | 黄金证据 |
|---|---|---|---|---|
| `case-043` | `cn-002600` | `fact_lookup` | `development` | `002600-2025FY-p2-s7 |
| `case-048` | `cn-300115` | `fact_lookup` | `test` | `300115-2024FY-p0-s0 |
| `case-054` | `cn-002600` | `fact_lookup` | `development` | `002600-2025FY-p2-s7 |
| `case-055` | `cn-002600` | `fact_lookup` | `development` | `002600-2025FY-p2-s7 |
| `case-056` | `cn-002600` | `evidence_location` | `development` | `002600-2025FY-p2-s7 |
| `case-057` | `cn-002600` | `scope` | `development` | `002600-2025FY-p2-s7 |
| `case-058` | `cn-002600` | `correct_refusal` | `development` | `002600-2025FY-p2-s7 |
| `case-062` | `cn-300115` | `fact_lookup` | `development` | `300115-2024FY-p0-s0 |
| `case-069` | `cn-300433` | `announcement_event` | `development` | `week10-event-impairment-001 |
| `case-070` | `cn-002600` | `correct_refusal` | `development` | `week10-event-litigation-001 |
| `case-071` | `cn-300433` | `risk_explanation` | `development` | `week10-risk-customer-concentration-001 |
| `case-072` | `cn-002475` | `announcement_event` | `development` | `week10-event-related-party-001 |
| `case-073` | `cn-002600` | `announcement_event` | `development` | `week10-event-buyback-001 |
| `case-074` | `cn-002600` | `risk_explanation` | `development` | `week10-event-guarantee-001 |

## 限制

- 本次结果是 BM25 工程对照，不代表向量检索或跨行业泛化。
- 新增题目全部为 development；原有 test 题保留，test 结果仅作冻结对照。
- 证据页匹配提高了对 span/chunk 版本差异的鲁棒性，但不能替代后续真实 chunk ID 对齐。
