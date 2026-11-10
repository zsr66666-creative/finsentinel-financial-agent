# ECS 原生部署、更新与回退

## 已验收与待验收

2026-11-11 用户反馈的服务器验收：Ubuntu 24.04、Node 22、Python 3.12、原生 PostgreSQL；数据库 connected；Nginx 页面及 CSS 为 200；standalone 启动 Ready；公网 API ONLINE，各页面和刷新正常。PostCSS 8.5.32 更新后服务器测试 10/10、生产构建成功、audit 为 0。这是用户提供的执行证据，并非维护者直连服务器验证。

当前是 synthetic_demo / deterministic-demo。HTTPS、域名备案、访问控制、备份恢复演练和持续稳定性待验收；容器部署仍未验收。

## 初次部署（服务器 Linux shell）

仓库目录为 /opt/finsentinel。安装 nginx、postgresql、python3-venv、Node 22；确认 node 路径为 /usr/bin/node。

创建专用 OS 用户 finsentinel，同时创建同名 PostgreSQL LOGIN 角色和其拥有的 finsentinel 数据库。后端服务模板通过 Unix socket peer 认证，不保存密码；依赖 Ubuntu 默认 peer 规则，不要改为 trust。

在仓库根目录安装后端：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e './backend[postgres]'
.venv/bin/python -m pip check
```

前端构建与资源打包，每一步成功再继续：

```bash
cd /opt/finsentinel/frontend
npm ci
npm test
NEXT_PUBLIC_API_URL="" NODE_OPTIONS="--max-old-space-size=1536" npm run build
mkdir -p .next/standalone/.next
cp -a .next/static .next/standalone/.next/
if [ -d public ]; then cp -a public .next/standalone/; fi
chown -R finsentinel:finsentinel /opt/finsentinel
```

将 deploy/ecs 的 service 模板复制到 /etc/systemd/system/。已有 standalone.conf drop-in 时先检查 systemctl cat finsentinel-frontend，避免旧覆盖改变模板。将 nginx.conf 中 YOUR_PUBLIC_IP_OR_DOMAIN 替换为实际地址，放入 sites-available 并链接到 sites-enabled；保留其他网站配置。

```bash
systemctl daemon-reload
systemctl enable --now finsentinel-backend finsentinel-frontend
nginx -t && systemctl reload nginx
```

只开放需要的 80（配置 TLS 后为 443），不公开 3000、8000、5432。前端空 API URL 使用同源 /api/，Nginx proxy_pass 不能增加尾斜杠剥离路径。

## 更新与回退

这是停机维护流程，不是零停机发布。先在仓库外备份：

1. 当前提交 SHA、服务和 drop-in 配置。
2. 同一版本的 package.json、package-lock.json、完整 .next、node_modules、public（若有）；检查空间，备份必须可读。
3. PostgreSQL 数据库：使用 pg_dump -Fc 输出到受保护文件，数据库和密钥不进 Git。

检查 git status，服务器本地依赖修改必须先同步或精确处理，不要用 reset --hard。停止 frontend 后更新代码、安装依赖、测试、构建、复制静态资源，再启动。后端依赖变更才需要更新后端并重启。每次构建都需要复制 static/public 到 standalone。

失败时停止继续操作，恢复匹配的完整构建产物和依赖、服务配置，daemon-reload 后启动。数据库变更另按迁移回滚方案处理，不能自动覆盖业务库。保留完整备份可避免恢复时必须重新构建。不要执行 npm audit fix --force。

## 验证与故障定位

- 启动后等待数秒，检查三个服务 active。
- 检查后端 8000 的 /health（数据库 connected），前端 3000 的根路径。
- 通过 Nginx 携带实际 Host 检查 /、/api/v1/companies、/health。
- 从当前页面 HTML 取出 JS/CSS 地址，检查返回 200；哈希会变化，不写死旧文件名。
- 浏览器确认 API ONLINE、告警/公司/复核/数据质量及刷新。
- npm audit --omit=dev；任何失败都不能宣称完成。

日志：journalctl -u finsentinel-frontend -n 60 --no-pager，以及 /var/log/nginx/error.log。注意时间：历史 Connection refused 可能只是维护停机，不表示当前失败。build 不会启动网站，必须执行 systemctl start。单 upstream 增加重试不能修复停止的进程。

## 后续事项

域名及适用的 ICP 备案、HTTPS、受控试用访问限制、备份恢复演练。当前演示含可修改状态接口；HTTP 不用于传输模型密钥或敏感数据。生产可用性未完成验收。
