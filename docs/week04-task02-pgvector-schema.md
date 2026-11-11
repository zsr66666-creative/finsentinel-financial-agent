# Week 4 Task 2：pgvector 结构准备

## 已完成

- 新增迁移 `002_document_chunk_embeddings`。
- PostgreSQL 会执行 `CREATE EXTENSION IF NOT EXISTS vector`，并创建 `document_chunk_embeddings`。
- 向量列使用 `VECTOR(dimensions)`；默认维度为 512。
- SQLite 本地测试使用 TEXT 占位列，保持轻量模式可测试。
- 表包含 `chunk_id`、`model`、`dimensions`、`embedding`、`text_sha256`、`created_at`，因此同一 chunk 可按模型和文本哈希追溯。
- 初始阶段不创建 ANN 索引；先精确检索，数据写入和召回评测后再决定索引。
- `migrate_vector_up` 可重复执行；`migrate_down(..., "002_document_chunk_embeddings")` 只删除向量表并保留基础迁移。

## 验证

```text
python -m pytest backend/tests/test_migrations.py -q
5 passed（连同 test_week03_migration_check.py）
```

本地验证覆盖 SQLite 的首次迁移、重复迁移和回滚。当前尚未在阿里云生产库执行该迁移，也尚未写入真实 embedding；Task 3 需要先冻结模型、维度和成本记录，再建立向量数据。

重复迁移检查维度约束；维度不匹配或未登记的同名表会拒绝继续。
基础迁移回滚前必须先回滚向量迁移。扩展由管理员提前启用；回滚不删除共享扩展。

## 设计边界

向量表不改变现有 `document_chunks` 和 BM25 路径。没有 embedding 或 pgvector 时，系统应继续使用 BM25；不能把表已创建描述为“已完成向量检索”。
