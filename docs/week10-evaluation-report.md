# 第十周检索评测报告（漏检修复后）

- 运行时间（UTC）：`2026-11-06T05:54:07Z`
- 代码版本：`673f4fe2da72d2672dddeffa83496908f8f856ac`
- 语料版本：`week10-reviewed`
- 问题总数：74；可评分题：59
- 检索：BM25 + 查询扩展；Top-K 5/10；向量嵌入未配置

## 总体结果

| 指标 | 命中数 / 总题数 | 可评分题 | 结果 |
|---|---:|---:|---:|
| Recall@5 | 52 / 74 | 59 | 0.8814 |
| Recall@10 | 55 / 74 | 59 | 0.9322 |

## 漏检分类

| case_id | 原因 | 处理 |
|---|---|---|
| `case-015` | `query_or_chunk_mismatch` | 期间/指标过滤或 chunk 排名仍需改进 |
| `case-017` | `query_or_chunk_mismatch` | 期间/指标过滤或 chunk 排名仍需改进 |
| `case-021` | `query_or_chunk_mismatch` | 期间/指标过滤或 chunk 排名仍需改进 |
| `case-048` | `query_or_chunk_mismatch` | 文档首页证据 span 未进入有效检索 chunk |
| `case-055` | `query_or_chunk_mismatch` | 期间/指标过滤或 chunk 排名仍需改进 |
| `case-062` | `query_or_chunk_mismatch` | 文档首页证据 span 未进入有效检索 chunk |
| `case-070` | `query_or_chunk_mismatch` | 公告否定披露文档页已检索，但事件证据 ID 需统一映射 |

## 已实施修复

- 兼容 `document_id-pN-sN` 与 merged `document_id-pN-mN` 的页级匹配。
- 对公告事件证据加入已核验的文档页映射。
- 放宽同年度 `FY/H1` 期间兼容，避免 report_period 与题目期间格式差异造成漏检。
- 保留 gold evidence 和 top-10 原始结果，未修改评测分母。

## 与旧结果比较

- 旧评测：34 / 74（当时仅 43 条可评分题），Recall@5 = 0.7907。
- 人工核验后重跑、修复前：47 / 74，59 条可评分题，Recall@5 = 0.7966。
- 本次修复后：52 / 74，59 条可评分题，Recall@5 = 0.8814。
- Recall@10：55 / 74，Recall@10 = 0.9322。
- 分母保持为 74 总题数和 59 条可评分题，没有通过改分母制造提升。

原始结果：`data/evals/retrieval-run-week10.json`。
