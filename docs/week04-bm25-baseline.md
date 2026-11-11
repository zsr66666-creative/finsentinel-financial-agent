# Week 4 Task 1：BM25 检索基线冻结

## 运行条件

- 运行时间：2026-11-11（本地工作区）
- 运行入口：`backend/app/run_retrieval_eval.py`
- 方法：`search_chunks` 的 BM25 词法检索，`top_k=5`，公司和报告期过滤
- 语料版本：`week7-8-v1`
- 题集：`data/evals/golden_questions.jsonl`，共 74 题；开发/测试划分：{'development': 62, 'test': 12}
- 冻结结果：`data/evals/retrieval-run-week04-bm25-baseline.json`

## 结果

- 全题命中数：9/74（仅作覆盖概览）
- 有黄金证据且纳入 Recall@5 分母的题目：59
- Recall@5：9/59 = 0.1525
- 检索模式：BM25；没有使用 embedding 或 RRF

Recall@5 只对有标注黄金证据的题目计分；无证据题、正确拒答题和未完成标注题不进入分母。全题命中数不能替代 Recall@5。

## 漏检记录

每题的 `retrieved_ids`、`gold_evidence_ids`、`warnings` 和 `miss_reason` 保存在结果 JSON 中。当前统一标记为 `query_or_chunk_mismatch`，Task 2 前需要进一步按分词、页面切分、同义词、公司/期间过滤和证据标注分别归因。

## 冻结边界

本结果仅作为 pgvector/RRF 对照基线。Task 2 以后不得修改本次 BM25 参数来追求向量结果；任何查询扩展、chunk 合并或过滤变化都必须另建实验文件并报告差异。该基线不证明真实模型质量，也不代表生产可用性。
