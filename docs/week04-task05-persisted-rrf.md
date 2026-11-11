# Task 5：同片段 BM25、pgvector 和 RRF

## 实现

入口为 `python -m scripts.vector_query hybrid`，其他参数与 search 相同。
加 `--disable-vector` 验证 BM25-only 路径。服务器无需加载模型。

两路共用导入表 provenance 中的原文片段、相同模型修订、公司、期间及 chunk_id。保留首批 -s ID，不伪造 -m 到 -s 映射，也不和旧合并片段直接融合。返回原文、来源、页码、两路排名及 RRF 分数。

BM25 参数：k1=1.2，b=0.75，正 IDF；沿用现有分词和查询扩展。每路候选深度 20，输出 K 为 1..20。RRF k=60，用排名而非原始分数；重复向量 ID 去重，拒绝候选语料以外的 ID，平分按 ID 稳定排序。

旧 search_chunks/HybridRetriever 的词法算法实际是词频求和，不是标准 BM25。week04-bm25-baseline 的命名和历史指标只能描述旧路径，不能当作新 BM25 的公平基线。Task 6 必须冻结同一切分和 ID 的新对照，分别报告词法算法变化与融合变化；不可把所有收益归因于向量或 RRF。

## 降级及范围

向量未配置、查询向量校验失败、向量查询异常或空结果时保留 BM25，明确返回 bm25_only 和安全错误类型，不返回内部异常详情。整个数据库不可用时无法加载词法语料，不承诺数据库故障时仍能检索。

历史时点检查沿用 fail-closed 逻辑：缺日期也排除。首批包缺 published_at，因此不能宣称真实历史查询通过。当前 CLI 尚未接入生产网页，不改动现有 API。

## 验证

本地相关测试 18 passed、1 skipped（PostgreSQL 集成需 TEST_POSTGRES_URL）。真实首批 10 片段及真实查询向量在本地执行排名/RRF smoke，通过；这不是云端 SQL 验收，也不是检索质量评测。

云端待验收：同一 query.json 使用 hybrid；再加 --disable-vector，检查两种模式、两路排名和来源；错误公司应返回空。服务器已有查询包，不需再次上传。尚未测量 Recall 改善。
