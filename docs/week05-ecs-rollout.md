# 第五周 ECS 分阶段上线

目标是阿里云实际可用；本地通过不等于上线完成。先备份/迁移并启用管理 API，再以单任务 worker 验收，最后启用常驻服务。本次无需构建前端。

## 第一阶段

更新到包含本脚本的提交后，在 root 终端执行 `bash deploy/ecs/enable-ingestion.sh`。脚本备份数据库并检查 dump 可读，显式应用 003/004，重复运行检查无新增迁移，生成不打印的管理 token，配置后端 EnvironmentFile、安装 worker unit，重启后端并检查 health。不会启用或启动 worker。数据库备份检查不等于恢复演练；依赖 pip check 失败即停止，不自动安装不匹配依赖。

## 第二阶段验收（另行执行）

仅从服务器 loopback 使用 token；不要通过当前公网 HTTP 发送凭据，不把 token 放入聊天或网页。Python 从 root-only env 文件读取凭据并调用 127.0.0.1:8000：先无凭据 401，再官方 URL 入队 202，重复键返回同 ID。运行服务用户 worker --once 后，鉴权查询应为 success/committed，保留来源 URL/final_url/acquired_at/SHA256、产物计数及页面提取范围。验收代码不硬编码未知报告业务归属。

真实采集成功后，以新任务重新采集同一披露，核对 blob/披露数不增加、任务数增加。失败/重试、运行中终止恢复必须在专用测试库演练，不向业务库插入伪造来源或改写租约时钟。采集产物不自动变成问答库文档或黄金证据。

## 第三阶段

观察 --once 的 journal、峰值内存/磁盘，再 `systemctl enable --now finsentinel-ingestion-worker`；unit 并发 1、MemoryMax=512M、KillMode=control-group，OOM 应记录为故障，不能当作成功。检查已有网站和 /compare 无回归。未获得实际输出前保持远端 pending。

## 停用与回退

先 `systemctl disable --now finsentinel-ingestion-worker`。移走本轮新增的 backend drop-in ingestion.conf（先确认内容/备份），daemon-reload 并重启后端即可关闭新管理入口；保留 token 文件 600 和备份。新增表不影响旧功能，默认保留取证，不自动 DROP 或恢复整个生产库。代码回退使用备份记录的已知版本并检查本地修改，禁止 reset --hard。数据库灾难恢复必须单独维护窗口评审与演练。

当前仅提交上线工具；未在 ECS 执行。重试入口容量核算及每进程限流边界见 Task 4 文档；管理入口只允许受信运维，不面向演示观众。
