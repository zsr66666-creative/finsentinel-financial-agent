# Week 16 Day 2：容器与 CI 一致性

## 已完成

- 前端镜像改用 `npm ci`，与 CI 的锁文件安装保持一致。
- 增加前后端 `.dockerignore`，避免把 `node_modules`、`.next`、虚拟环境、测试缓存和本地数据库复制进构建上下文。
- Compose 保留后端健康检查，并让前端等待 `service_healthy` 后启动。
- CI 使用 Python 3.12、Node 22 和锁文件安装，覆盖后端导入/pytest、前端测试/生产构建。

## 验证命令

```powershell
# 静态检查
podman compose -f compose.yaml config

# 完整容器验收（需要可访问镜像仓库）
podman compose -f compose.yaml build
podman compose -f compose.yaml up -d
curl http://localhost:8000/health
curl http://localhost:3000
podman compose -f compose.yaml down
```

## 验收边界

当前环境是否能完成镜像拉取取决于 Podman machine 和 Docker Hub 网络；无法拉取时只能记录为环境阻塞，不能把静态 Compose 检查当成端到端通过。
