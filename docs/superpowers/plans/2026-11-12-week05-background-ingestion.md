# 第 5 周后台采集 Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. This document authorizes planning only; implementation follows a separate user instruction.

**Goal:** 将官方 PDF 采集改为可恢复、可审计的后台任务，不改变现有演示入口语义。

**Architecture:** PostgreSQL 持久队列 + 独立单进程 worker。API 只提交/查询任务，worker 执行下载和解析；复用现有解析器及来源策略，使用租约、阶段检查点和内容寻址文件实现至少一次执行与幂等提交。

**Tech Stack:** 现有 FastAPI、SQLAlchemy、psycopg、requests、PyMuPDF、systemd；首版不增加 Redis/Celery，不在采集 worker 加载 embedding 模型。

## 现状核对

- `backend/app/ingestion/pipeline.py` 已有 SafeDownloader、精确官方域名白名单、HTTPS、DNS 公网地址检查、逐跳重定向校验、32 MiB 限制、PDF magic 检查、下载重试和原子 JSON 文件。
- `acquire_and_extract` 已有本地文件复用，但 CLI 使用 ThreadPoolExecutor，不提供持久任务领取、租约、任务级重试或故障恢复。
- `POST /api/v1/admin/ingestion/jobs` 只接受 demo_refresh，即刻记录 completed，documents_processed=0。不能称为真实采集队列；保持兼容，不将旧 completed 记录强行迁入新状态机。
- 本次只形成计划，没有完成迁移、worker、接口鉴权或服务器安装。

## 方案选择

| 方案 | 优点 | 限制 | 决定 |
| --- | --- | --- | --- |
| FastAPI BackgroundTasks | 依赖少 | 进程重启丢任务，缺领取和恢复语义 | 不采用 |
| PostgreSQL 队列 + worker | 复用数据库、事务领取、减少常驻组件 | 需自行实现租约和幂等 | 首版采用 |
| Redis + Celery | 调度能力成熟 | 增加内存、组件和运维负担 | 规模需要时另评估 |

## 固定契约

### 数据与状态

新专用表 `source_ingestion_tasks`，不复用 Store JSON put 实现并发领取。字段：UUID id、source_url、company_code、report_period、report_type、idempotency_key、request_sha256、status、stage、attempts、max_attempts、next_attempt_at、lease_token、lease_until、created_at、started_at、finished_at、requested_url、final_url、acquired_at、sha256、artifact_path、document_id、error_code。UTC 时间使用 TIMESTAMPTZ。

状态仅 pending/running/success/failed；stage 为 queued/downloaded/parsed/committed。max_attempts 默认 3；每次领取 attempts+1，失败到 failed；可重试错误且次数未满时设置 next_attempt_at（首次 30 秒、第二次 120 秒），worker 将到期 failed 重新排队。人工 retry 仅允许 failed 且次数未满，返回同一 task ID；达到上限返回 409，不静默重置预算。

pending→running 由事务领取，`FOR UPDATE SKIP LOCKED`；运行时租约 180 秒，每 30 秒独立心跳。worker 崩溃后过期租约回收为 failed/worker_lease_expired，可按剩余预算恢复。所有进度/最终提交必须匹配 lease_token，过期 worker 不可覆盖新 owner。首版并发 1。

请求幂等：幂等键唯一，相同键+同请求哈希返回原任务；相同键不同请求返回 409。原始 PDF 以 SHA256 命名、原子发布，blob 哈希唯一；披露记录以公司+期间+报告类型+哈希唯一，不同来源 URL 可作为来源关联保存。同 URL 内容变化保留新哈希版本；不能仅按 URL 永久去重。解析产物以 PDF 哈希+解析器版本寻址。

### 来源、权限和资源

- 复用现有五个精确 host：static.cninfo.com.cn、www.cninfo.com.cn、www.sse.com.cn、static.sse.com.cn、disc.static.szse.cn。不允许通配后缀、HTTP、凭据、非法端口、片段或非公网地址；每跳最多 3 次重定向，目标重新校验，禁止关闭 TLS。
- 下载连接超时 8 秒、读取超时 45 秒，新增总下载截止 120 秒；32 MiB 上限，PDF magic 和解析校验。安全拒绝及 4xx 不自动重试；超时/连接故障/429/5xx 可按任务预算重试。worker 路径关闭 SafeDownloader 内部重试，防止双层重试扩大请求量。
- DNS 预检查与 requests 二次解析间仍有 TOCTOU 风险：实现固定到已验证 IP 的连接并保留原 hostname 的 SNI/证书校验；测试模拟二次解析切到私网。未解决前仅允许人工受控 CLI，不开放网络任务提交。
- 新写接口先要求专用管理 token（环境变量，无默认值、失败时关闭），限制入队数量、请求频率并不回传 token。公网演示用户只能查看经脱敏的结果；新任务写入口首版不接网页。现有 demo_refresh 不被当作授权下载入口。
- 路径均由服务器生成并限制在专用 data 目录，客户端不能传本地路径。解析在独立子进程执行，单次 120 秒截止，worker memory 上限目标 512 MiB、并发 1；服务器实测后调整，不能预先声称足够。
- 断点续跑仅指阶段恢复，不支持 HTTP Range 字节续传：下载完成校验哈希后复用 PDF，解析完成复用版本匹配产物，committed 阶段重复执行不新增文档。半成品仅写临时文件，校验失败不得复用。

## 执行顺序与验收

### Task 1：持久队列与状态机（本地 PostgreSQL 并发与租约验收通过，ECS 未部署）

实现记录见 `docs/week05-task01-queue.md`。首次本地回归为 16 passed、1 skipped；补充独立 PostgreSQL 18.6 实例后，队列和迁移测试 8 passed、0 skipped，并发/租约专项重复 10/10 通过，0 残留 schema。实例已停止；不是 ECS 16.15 验收。下方步骤保留完整执行说明。

**Files:** 新建 `backend/app/ingestion/task_queue.py`、`backend/migrations/003_source_ingestion_tasks.py`、`backend/tests/test_ingestion_queue.py`；修改 `backend/app/migrations.py`。

**Interfaces:** enqueue_task(engine, request, idempotency_key) -> task；claim_task(engine, now) -> task|None；heartbeat(engine,id,token,now) -> bool；finish_task(engine,id,token,result) -> bool；retry_task(engine,id,now) -> task。

- [ ] 先写失败测试：同幂等键同请求返回相同 ID；异请求 409；两个 PostgreSQL 连接同时领取只能有一个 owner；过期 token 无法提交；超预算重试被拒。
- [ ] 执行 `python -m pytest backend/tests/test_ingestion_queue.py -q`，记录失败，再实现表约束和事务更新。
- [ ] 复跑并在专用 TEST_POSTGRES_URL 测并发及租约回收；SQLite 不能替代这两项，未配置时明确 skipped。
- [ ] 验证迁移重复运行无新增操作、旧演示记录不变后精确提交。

### Task 2：来源及流式下载边界（未实现）

**Files:** 新建 `backend/app/ingestion/source_policy.py`、`backend/tests/test_ingestion_download_policy.py`；修改 `backend/app/ingestion/pipeline.py`。

**Interfaces:** download_pdf(url, destination, deadline_seconds=120) -> {requested_url,final_url,acquired_at,sha256,bytes,path}；失败抛结构化 error_code/retryable，不将内部网络错误原文作为公开响应。

- [ ] 先写失败测试：白名单伪后缀、私网 DNS、重定向越界、缺 Location、DNS 换绑、流超限、慢流总超时、HTML 冒充 PDF、TLS 错误均拒绝；允许 host 内合法跳转正常。
- [ ] 执行 `python -m pytest backend/tests/test_ingestion_download_policy.py backend/tests/test_ingestion_pipeline.py -q`，记录失败后实现策略，复用已有安全行为。
- [ ] Mock 控制时间和网络，不使用外网不稳定结果作单测依据；再用一条已核实官方 URL 做单独人工联网验收，保存真实 final_url/抓取时间/哈希。
- [ ] 确认无环境代理、无 TLS 降级、无双层重试后提交。

### Task 3：单 worker、阶段恢复与内容去重（未实现）

**Files:** 新建 `backend/app/ingestion/worker.py`、`backend/app/ingestion/artifacts.py`、`backend/tests/test_ingestion_worker.py`；复用 pipeline 解析逻辑。

**Interfaces:** run_once(engine, artifact_root, downloader, parser) -> bool；worker CLI 支持 --once 和连续轮询；产物注册与任务 success 在一个数据库事务提交。

- [ ] 先写失败测试：相同文件不同任务只保存一个 blob/相同披露一条；同 URL 新内容保留版本；下载后 kill 重启不重复下载；解析后重启不重复解析；失效租约提交被拒。
- [ ] 执行 `python -m pytest backend/tests/test_ingestion_worker.py -q`，记录失败后实现；模拟可重试超时与不可重试来源拒绝。
- [ ] 验证下载和解析都不持有领取事务长锁，独立心跳更新；解析子进程超时被清理，临时文件不作为检查点。
- [ ] 保存两轮运行记录、文件计数及数据库行数，再提交。

### Task 4：管理接口与查询接口（未实现）

**Files:** 新建 `backend/app/ingestion/routes.py`、`backend/tests/test_ingestion_task_api.py`；修改 `backend/app/main.py`、`backend/app/schemas.py`。

**Interfaces:** POST /api/v1/admin/source-ingestion/tasks（202，新任务或已有任务）；GET /api/v1/admin/source-ingestion/tasks/{id}；POST 同路径 /retry；管理 token 必须配置且校验通过。每次最多提交一个明确官方 URL。

- [ ] 先写失败测试：无凭据 401/未配置功能 503；非法来源 422；幂等冲突和非法 retry 409；查询未知 ID 404；日志/响应不含 token 或数据库 URL。
- [ ] 执行 `python -m pytest backend/tests/test_ingestion_task_api.py -q`，记录失败后接入独立 router。保留旧 demo_refresh 行为和文案。
- [ ] 确认 API 202 仅表示入队，不伪装下载完成；查询展示四种状态及阶段，错误脱敏后提交。

### Task 5：本地故障验收、ECS 部署与记录（未实现）

**Files:** 新建 `deploy/ecs/finsentinel-ingestion-worker.service`、`docs/week05-ingestion-acceptance.md`；修改 `docs/ecs-native-deployment.md`。

- [ ] 运行 Task 1–4 全部测试；PostgreSQL 集成必须使用专用测试库，不在生产表制造故障。
- [ ] 首版 worker 独立 systemd 用户 finsentinel、并发 1、MemoryMax=512M、Restart=on-failure；任务存储目录最小权限，管理 token 文件 600。
- [ ] 部署前备份数据库并审核迁移，先执行一次 --once；用一份官方 PDF 验证来源链、一次失败单独重试、worker kill 恢复和重复采集不新增披露。
- [ ] 记录版本、来源 URL、final_url、SHA256、任务数、blob/文档数、尝试次数、耗时和峰值 RSS；观察网站健康无回归后才启用连续 worker。
- [ ] 更新状态清单和剩余限制，精确提交；线上部署、恢复演练和人工业务验收分别记录，不用单元测试代替。

## 总验收和本轮交付

Task 1–5 顺序依赖；Task 2 来源边界未完成前不开放真实网络入队。第 5 周完成要求：重复任务/内容不重复建文档，单任务可重试，阶段恢复有效，来源链完整，非法来源/超时/越界重定向被拒，远端 worker 实测有记录。

本轮仅完成仓库核对、方案选择、状态和来源契约及任务拆分；上面所有实现步骤保持未勾选。第 4 周限定比较页面无需因本计划重启或重建。
