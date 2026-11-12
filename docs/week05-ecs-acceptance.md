# 第五周阿里云上线验收

依据用户粘贴的 ECS 输出及浏览器确认整理，不是维护者直连服务器。部署版本 c0a41e577e415f5db56e07230e01ac3bada3116f，通过已校验 SHA256 的离线 Git bundle 快进更新；GitHub HTTPS 拉取失败未关闭 TLS。

| 检查 | 状态与证据 |
| --- | --- |
| 数据库备份 | dump 可读；目录 /root/finsentinel-ingestion-backup-20261112-223940；未恢复演练 |
| 003/004 迁移 | 首次成功，repeat=[] [] |
| 后端依赖与健康 | pip check 无破损，health ok、PostgreSQL connected |
| 管理鉴权 | 无凭据 401；凭据仅服务器 loopback 使用，未公开 |
| 请求幂等 | 相同键返回同一任务 ID，PASS |
| 单次官方采集 | 5958ae18-8ac8-4c2f-bb30-e14a38755ecc，success/committed，attempts=1 |
| 常驻 worker | 已 enable/start，active/running，NRestarts=0（当次快照） |
| 重复内容 | 新任务 9db0f7d6-4fc8-4905-9d9c-d8e09b2b0302 成功，同 document_id，matching_documents=1 |
| 资源快照 | MemoryCurrent=90828800 bytes，MemoryPeak=141926400 bytes；不是持续负载测试 |
| 网站回归 | 正确 Host 下 / 与 /compare 均 HTTP 200；health ok |
| 外部浏览器 | 用户确认网站可打开，母公司比较结果、差额与 62/63 页证据符合预期 |

采集 URL/final_url：https://static.cninfo.com.cn/finalpage/2025-04-26/1223326862.PDF 。SHA256 e436b5ab1775cfa05aacb4a16dd8e5c6b89e926ed18a7a55a86728bab6fcb1da；document_id 05e081ae37a01bc1df83183f2b93c64590d2c2aac6dd4d0c9864743de1b105c4。首次抓取时间为用户输出的 2026-11-12T22:43:21.606743+08:00。公司/期间为提交任务的元数据，采集成功不单独证明业务归属经过人工核验。

## 完成范围和剩余门槛

第五周核心采集链路已在 ECS 上线并验证：鉴权管理接口→持久队列→后台 worker→真实下载解析→幂等/内容去重→来源信息。现有网页正常；采集管理尚无网页入口，仅受信运维接口，不自动将产物发布到问答语料或生成 embedding。

本地 PostgreSQL 的失败事务和进程退出恢复已验证；ECS 专用测试库中的失败重试、崩溃恢复、非法来源/重定向/超时，以及备份恢复演练尚未执行。保留为 pending；不能将单次正常采集等同这些故障验证，也不宣称第五周全部验收或全站生产可用。限流每 API 进程、人工重试容量核算等限制见 Task 4 文档。

## ECS 故障与恢复补验（用户提供完整输出）

专用测试库执行相关 pytest：22 passed，1 warning（Starlette TestClient 的 httpx 弃用提示，不是失败）；worker 故障专项 4/4 通过，包含两个阶段突然退出恢复、事务注入失败回滚及真实官方下载解析。故障注入不在生产任务表执行，租约时间显式推进；不等同真实等待或全机断电演练。

首次恢复因 postgres 拥有的 vector 扩展 COMMENT 权限失败；修改 pg_restore 使用 --no-comments，在新空库重试成功。服务器脚本存在该精确本地修改；后续 git 更新前须核对，不能直接覆盖。

恢复目标 finsentinel_restore_test_20261112231355，PostgreSQL 16.15；同一导出快照的 18 张 public 表记录数与恢复库全部一致。其中 companies=24、filings=48、document_chunks=288、evidence_spans=292、financial_metrics=288、document_chunk_embeddings=14、source_ingestion_tasks=2、ingestion_artifacts=1。production 仅只读导出，未覆盖。后端/前端/worker 均 active，health ok、PostgreSQL connected。

第五周核心交付与上述 ECS 验收已完成。历史 pending 中数据库恢复、专用测试库故障重试/阶段恢复已由本节证据补齐；来源/重定向/超时来自服务器上 mock 单测，不声称真实恶意网络演练。备份仅验证 schema/表计数恢复，不是逐行校验、应用切换或全机灾备。每进程限流、retry 容量核算、无采集网页管理入口等已知限制继续保留。测试库和验收文件暂保留，不自动删除。

下一阶段为第六周真实公司扩展；先核对已有真实来源和覆盖情况，不能将数据库 24 条公司记录全部当作已核验真实公司。
