# Task 4：持久向量 Top-K

实现：backend/app/pgvector_search.py；操作入口：python -m scripts.vector_query。

使用 PostgreSQL pgvector 精确 cosine distance 排序，升序并按 chunk_id 稳定打破平分；不使用空表训练的 ANN 索引。先过滤模型及修订版、512 维、公司和期间，再 LIMIT（1..20）。返回距离、相似度、耗时、来源及页码，排序不表示事实已核实。

查询在本地用 BAAI/bge-small-zh-v1.5 的固定修订 7999e1d3359715c523056ef9478215996d62a620 生成，使用中文检索前缀；服务器只接收查询向量，不加载模型。私有查询文件位于 outputs/vector-batch/query.json，不提交 Git。

可选 --as-of YYYY-MM-DD 会排除未来或缺失 published_at 的片段。首批导入包尚未保存 published_at，因此历史时点查询会返回空，不能据此宣称真实历史时点检索验收通过。后续需重新导出完整元数据并受控更新来源列。

本地验证：10 passed，1 skipped。跳过项是 TEST_POSTGRES_URL 未配置的 PostgreSQL 集成测试。该集成测试使用临时表和回滚事务，覆盖精确命中、错误公司、错误期间、未来材料和无结果，不更改业务表。需要已有 vector 扩展。

服务器验收待完成：上传查询包，校验 SHA-256 后运行 search，检查结果 ID/页码/来源；用不存在的公司和期间复跑，应为空。当前只提供 CLI 和可复用检索函数，尚未接入网页 API，未完成 RRF，也没有测量 Recall 改善。首批仅 10 个片段，不能据此计算完整题集质量。
