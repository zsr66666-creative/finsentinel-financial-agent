# Task 2 官方来源下载边界

新增 `app.ingestion.source_policy.download_pdf(url,destination)`，单次执行、不内部重试。返回 requested_url/final_url/acquired_at/sha256/bytes/path；DownloadError 提供稳定 code 和 retryable，不暴露底层网络错误。429/5xx/网络故障可重试，来源拒绝、TLS、大小、格式错误不可重试。

官方域名精确匹配，HTTPS、无凭据、无非标准端口、无 fragment/控制字符。逐跳校验，最多 3 跳；缺 Location 拒绝。生产 transport 校验 DNS 所有候选地址均为公网，固定选定 IP 建立 TCP，官方 hostname 保留为 SNI、证书 assert_hostname 和 Host。urllib3 直连不读取环境代理、不自动重定向或重试。该模块直接使用 urllib3，依赖由 pyproject 显式声明。

流式写入同目录临时文件，32 MiB 上限、Content-Length 合理性与完整长度、identity 编码、PDF magic 校验；独占硬链接发布，不覆盖已有目的文件，失败清理临时文件。完整 PDF 解析在后续 worker 的隔离子进程执行，magic 通过不能算有效财报。

120 秒 deadline 在网络操作前后检查，connect≤8秒、read≤45秒。它不是强制进程截止：DNS 系统调用和已阻塞的 socket 操作不能被 Python 时钟检查立即中止。因此真实下载开放前仍需 worker 进程级总截止与清理验收；不能宣称严格 120 秒硬截止已完成。

本轮来源和下载策略单元测试使用可控 transport/时间/DNS，覆盖固定 IP、SNI/Host/TLS 配置、私网拒绝、跳转越界/缺目标/合法跳转、大小、magic、总时钟超限、编码、截断、HTTP 分类和 TLS 错误脱敏。它们不是公网真实 TLS 连接验收，也未以真实 DNS 换绑网络服务器演练。

相关测试 27 passed、1 skipped（队列 PostgreSQL 测试本轮未配置连接；此前单独实测记录不变）。没有修改旧 SafeDownloader 或 CLI 行为，没有开放下载 API，没有连接阿里云，也未下载官方 URL。旧路径的 DNS 检查局限仍存在，不把新模块的安全属性归于旧路径。

当前状态：Task 2 新模块及本地策略验证完成；官方 URL 实际联网验收、进程级截止及 worker 接入仍 pending。后续先接入 Task 3 隔离 worker，完成硬截止后再受控核验一个官方 URL，保存来源链及哈希，之后才开放入队。
