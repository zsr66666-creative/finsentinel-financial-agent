# 第 5 周 Task 1：持久队列基础

新增独立 source_ingestion_tasks 表及 003 迁移，未改动旧 ingestion_jobs 演示记录。迁移需显式调用 migrate_ingestion_up，不在应用启动时自动执行。可回滚本表；初始迁移回滚前须先回滚 003，防止遗失版本记录。

task_queue 提供 enqueue_task、claim_task、heartbeat、finish_task、retry_task。相同幂等键与请求/预算返回原记录；冲突拒绝。状态 pending/running/success/failed，领取计数上限 1–3；失败自动重试间隔 30/120 秒。人工 retry 不重置预算。PostgreSQL 使用事务与 FOR UPDATE SKIP LOCKED；租约 180 秒，心跳仅允许未过期 owner。过期回收保留阶段，旧 token 不可提交。

队列层仅检查来源 URL 静态白名单，不下载、不做 DNS 或网络访问；尚未完成 Task 2 安全下载边界，因此没有接入真实任务 API。finish_task 的 success 表示受信调用方提交完成，不自行证明文件或产物存在。阶段检查点更新、产物事务提交和周期心跳将在 worker 任务实现，不把本队列原语当作完整 worker。

SQLite 用于状态/幂等顺序测试，不支持并发 worker 验收。可选 PostgreSQL 测试在 TEST_POSTGRES_URL 中创建 UUID 临时 schema，验证双连接争抢及过期 owner；最终仅删除该测试 schema。必须专用测试库并具备创建 schema 权限，不能指向生产库。

```text
PYTHONPATH=backend;.
python -m pytest backend/tests/test_ingestion_queue.py backend/tests/test_migrations.py -q
```

当前未在阿里云执行迁移、没有新增 worker/systemd、没有触发下载。未配置 TEST_POSTGRES_URL 时并发测试明确跳过，不能宣称 PostgreSQL 并发已验证。上线前还需专用 PostgreSQL 实测、迁移备份及后续任务验收。
