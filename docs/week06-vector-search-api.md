# Task 6：真实向量与混合检索 API

新增 `POST /api/v1/evidence/search/vector`。接口接收外部生成的 512 维查询向量，在 PostgreSQL `document_chunk_embeddings` 中按公司、报告期、模型和可选披露日期过滤，执行 pgvector cosine Top-K；同时用同一批 chunk 的词法排名执行 RRF。

接口不在 1.7 GiB ECS 进程中加载 embedding 模型，因此不会伪造查询向量，也不会把 `/compare` 的已复核结构化契约改成开放式问答。`vector` 缺失、维度错误或非有限值返回 422；数据库不可用返回不泄露连接细节的 503；返回中带有 `retrieval_mode`、`warnings`、`duration_ms` 和 `data_mode`。

模型生成仍是独立边界：本地或专用 embedding 服务生成 `BAAI/bge-small-zh-v1.5` 的 512 维向量后，调用该接口。下一步再用固定问题集做云端延迟与 Recall 对照。
