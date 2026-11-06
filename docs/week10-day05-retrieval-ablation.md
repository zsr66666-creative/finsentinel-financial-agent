# 第十周 Day 5：检索消融与向量检索状态

## 运行元数据

- 运行时间（UTC）：`2026-11-06T01:22:24Z`
- 代码版本：`dc79d73c64aea0d5adadd7abc0435fce7ada89a2`
- 语料版本：`week10-multi-company-v3`
- 黄金问题总数：74
- Top-K：5

## 可运行实验

| 实验 | 状态 | 命中数 / 总题数 | 可评分题 | Recall@5 |
|---|---|---:|---:|---:|
| `retrieval-run-week10-bm25` | completed | 24 / 74 | 43 | 0.5581 |
| `retrieval-run-week10-query-expansion` | completed | 29 / 74 | 43 | 0.6744 |
| `retrieval-run-week10-chunk-merge` | completed | 29 / 74 | 43 | 0.6744 |

## 向量与混合检索

| 实验 | 状态 | 结果 |
|---|---|---|
| `vector_retrieval` | 未配置 | 当前环境没有 embedding 模型或向量服务，未生成向量指标。 |
| `hybrid_bm25_vector_rrf` | 未运行 | 需要真实 embedding provider；测试用假 embedder 不用于评测。 |

## 结论

- 当前可复现的最佳结果是查询扩展：29 / 74，Recall@5 = 0.6744。
- chunk 合并/证据加权与查询扩展并列：29 / 74，Recall@5 = 0.6744。
- 与基础 BM25 相比，查询扩展提升 5 个命中，Recall@5 从 0.5581 提升至 0.6744。
- 当前不能声称向量检索或混合检索已经提升，因为环境没有真实向量模型，相关结果标记为未配置/未运行。

## 后续建议

- 如果要运行向量消融，需要先配置可复现的 embedding provider、模型版本和离线缓存。
- 配置完成后必须重新运行全部 74 条题，并单独记录耗时、模型版本和失败回退情况。
- 在向量实验完成前，第十周默认检索策略使用查询扩展版本。

原始实验文件：
- `data/evals/retrieval-run-week10-bm25.json`
- `data/evals/retrieval-run-week10-query-expansion.json`
- `data/evals/retrieval-run-week10-chunk-merge.json`
- `data/evals/retrieval-run-week10-ablation.json`
