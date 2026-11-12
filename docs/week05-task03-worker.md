# Task 3 worker 本地实现记录

新增独立 `python -m app.ingestion.worker --artifact-root <服务器专用目录> --once`；未加 --once 时持续轮询，单 worker。生产 CLI 要求 PostgreSQL，显式先运行队列 003 和产物 004 迁移；不自动迁移或启动线上服务。

下载及解析默认分别在 spawn 子进程执行；父进程每 0.2 秒检查、120 秒阶段截止，超时 terminate 后必要时 kill；每 30 秒独立数据库心跳，租约丢失停止。该截止包含 DNS 阻塞，不仅是下载器协作式时钟检查。进程启动本身、操作系统调度与 terminate 清理会有额外延迟，不承诺精确到毫秒。

下载后校验 SHA256 并发布内容寻址 blob，保存 downloaded 检查点；恢复时只有文件哈希匹配才复用。解析结果按披露身份哈希与 PyMuPDF 版本存储，文件存在且内含 PDF 哈希/版本匹配时复用；parsed 检查点后，持有效租约在同一数据库事务登记 ingestion_artifacts 和任务 success。披露身份由公司/期间/报告类型/PDF 哈希组成，同内容不同来源任务保留各自 requested/final URL，不重复登记同一披露；变更内容生成另一身份。临时目录清理失败记录 warning，不冒充清理成功。

注入 downloader/parser 仅供测试，绕过进程隔离；生产 CLI 不提供该选项。解析产物尚无额外文件校验和，当前按 JSON 内嵌哈希/版本判断，不防御同权限本地文件篡改。存储目录必须仅服务用户可写。解析器对长报告仍采用既有选页逻辑，不代表全页提取。此 worker 不生成 embedding、不触发网页分析，也不替换现有 document_chunks。

## 已执行

- 本地相关测试 33 passed、1 skipped；跳过本轮未配置的 PostgreSQL 队列集成，先前独立验收保持有效。
- 解析失败后重新排队复用 PDF（下载调用次数不增加）；重复内容 blob 与披露注册计数为 1。
- 004 迁移重复运行、回滚顺序检查通过。
- 超时终止逻辑单测通过；另在本机实际 spawn PyMuPDF 子进程解析生成测试 PDF 成功，并以 0.001 秒截止实际触发 stage_timeout。

## 待验收，不宣称 Task 3 全部完成

真实 PostgreSQL 上产物登记与 success 原子提交、worker 父进程 kill 后恢复、解析完成后崩溃重跑、同 URL 内容更新、心跳失效下运行中子进程中止、官方 URL 下载来源链及 RSS/磁盘资源限制均待独立验收。未部署 ECS、未增加 systemd、未对外开放入队接口。当前实现仅单 worker，不宣称并发解析同一身份产物安全。
