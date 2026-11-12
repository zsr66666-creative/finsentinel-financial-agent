# Task 4 管理采集接口

Task 3 本地关键门槛通过后实现，未部署 ECS。新接口默认关闭：INGESTION_ADMIN_TOKEN 未设置或不足 32 字符返回 503；Bearer token 恒定时间比较，失败 401。生产要求 PostgreSQL、显式 003 迁移；不自动迁移或启动 worker，旧 demo_refresh 保持原样。

- POST /api/v1/admin/source-ingestion/tasks：一个官方 URL，company_code 六位数字、report_period=YYYYFY/H1/Q1–4、report_type=annual/half_year/quarterly/announcement，Idempotency-Key 必填。202 仅为入队；相同键同请求返回原任务，不同请求 409。
- GET /api/v1/admin/source-ingestion/tasks/{uuid}：经鉴权查询，未知 404。
- POST 同路径 /retry：经鉴权，仅 failed 且预算未耗尽；不会重置 attempts，不满足 409。

写操作每进程每分钟最多 10 次；创建新任务时 PostgreSQL advisory lock 串行化容量检查与入队，pending/running 上限 100。该限流是单 API 进程限制，重启清零，不宣称分布式限流；人工 retry 的容量重新核算仍待完善。专用管理 token 不提供给公网浏览器或写进代码，部署前以 600 权限环境文件注入。查询返回脱敏任务信息，不含 lease_token、artifact_path、数据库 URL 或管理 token。公开只读任务查询尚未提供。

本地真实 PostgreSQL 18.6 隔离 schema 验证 HTTP 入队/幂等/冲突/查询/非法重试/失败重试通过；与 worker、来源、迁移及比较接口回归共 46 passed、0 skipped。表和 schema 均隔离；不是阿里云 HTTP 验收。Task 5 需要数据库备份、显式迁移、worker systemd 与资源限制、官方来源和失败恢复实测；在此之前不启用线上入队。
