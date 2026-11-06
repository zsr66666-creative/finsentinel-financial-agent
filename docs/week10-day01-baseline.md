# 第十周 Day 1：检索基线

## 基线状态

- 冻结时间（UTC）：`2026-11-06T00:51:43Z`
- 代码版本：`0c4802fe4f02f4e2f4a31bec3aa75ea391de172f`
- 来源评测：`week09-multi-company-bm25-001`
- 语料版本：`week8-multi-company-v2`
- 问题集：`data/evals/golden_questions.jsonl`
- 总题数：48
- 检索模式：`bm25_only`，Top-K = 5
- 向量嵌入：未配置（BM25-only）

## 总体基线

| 范围 | 命中数 / 总题数 | 可评分题 | Recall@5 |
|---|---:|---:|---:|
| 全部 | 9 / 48 | 17 | 0.5294 |
| development | 7 / 36 | 13 | 0.5385 |
| test | 2 / 12 | 4 | 0.5000 |

## 按公司

| 公司 | 公司 ID | 命中数 / 总题数 | 可评分题 | Recall@5 |
|---|---|---:|---:|---:|
| 立讯精密 | `cn-002475` | 9 / 40 | 9 | 1.0000 |
| 歌尔股份 | `cn-002241` | 0 / 2 | 2 | 0.0000 |
| 领益智造 | `cn-002600` | 0 / 1 | 1 | 0.0000 |
| 长盈精密 | `cn-300115` | 0 / 3 | 3 | 0.0000 |
| 蓝思科技 | `cn-300433` | 0 / 2 | 2 | 0.0000 |

## 按题型

| 题型 | 命中数 / 总题数 | 可评分题 | Recall@5 |
|---|---:|---:|---:|
| 事实查找 (`fact_lookup`) | 3 / 18 | 11 | 0.2727 |
| 跨期计算 (`calculation`) | 2 / 9 | 2 | 1.0000 |
| 范围判断 (`scope`) | 1 / 1 | 1 | 1.0000 |
| 正确拒答 (`correct_refusal`) | 1 / 1 | 1 | 1.0000 |
| 证据定位 (`evidence_location`) | 1 / 6 | 1 | 1.0000 |
| 证据支持 (`evidence_support`) | 0 / 1 | 0 | N/A |
| 规则判断 (`rule`) | 1 / 1 | 1 | 1.0000 |
| 公告事件 (`announcement_event`) | 0 / 4 | 0 | N/A |
| 风险解释 (`risk_explanation`) | 0 / 4 | 0 | N/A |
| 同业比较 (`peer_comparison`) | 0 / 3 | 0 | N/A |

## 当前漏检清单

当前共有 **8 条可评分漏检**，全部来自新增公司，均记录为 `query_or_chunk_mismatch`。

| case_id | 公司 | split | 题型 | 黄金证据 | 漏检原因 |
|---|---|---|---|---|---|
| `case-041` | `cn-002241` | `development` | `fact_lookup` | `002241-2025FY-p8-s16` | `query_or_chunk_mismatch` |
| `case-042` | `cn-002241` | `development` | `fact_lookup` | `002241-2024FY-p8-s16` | `query_or_chunk_mismatch` |
| `case-043` | `cn-002600` | `development` | `fact_lookup` | `002600-2025FY-p2-s7` | `query_or_chunk_mismatch` |
| `case-044` | `cn-300115` | `development` | `fact_lookup` | `300115-2025FLASH-p1-s14` | `query_or_chunk_mismatch` |
| `case-045` | `cn-300115` | `development` | `fact_lookup` | `300115-2025FLASH-p1-s14` | `query_or_chunk_mismatch` |
| `case-046` | `cn-300433` | `development` | `fact_lookup` | `300433-2024FY-p7-s0` | `query_or_chunk_mismatch` |
| `case-047` | `cn-300433` | `test` | `fact_lookup` | `300433-2025SUMMARY-p4-s0` | `query_or_chunk_mismatch` |
| `case-048` | `cn-300115` | `test` | `fact_lookup` | `300115-2024FY-p0-s0` | `query_or_chunk_mismatch` |

## Day 1 结论

第十周后续改进应优先处理歌尔股份、领益智造、长盈精密和蓝思科技的查询词与证据 chunk 对齐问题。立讯精密基线保持为 9 / 9 可评分题命中，后续调参不得破坏该结果。

后续所有第十周实验必须以本文件作为对照，并单独记录实验版本、运行时间、代码版本和漏检变化。

原始评测明细：`data/evals/retrieval-run-week09.json`。
