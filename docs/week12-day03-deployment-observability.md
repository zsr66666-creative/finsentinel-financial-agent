# Week 12 Day 3：部署配置与运行可观测性

## 完成内容

- Compose 后端增加 `/health` 容器健康检查。
- Compose 前端增加首页 HTTP 健康检查。
- 前端等待后端健康后再启动，避免启动顺序导致的误报连接失败。
- Compose 环境变量提供安全默认值：`DATA_MODE=synthetic_demo`、SQLite 数据库和本地 CORS。

## 启动与排障

```cmd
docker compose up --build
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
```

两个服务状态应为 `healthy`。后端日志出现异常时先访问 `http://localhost:8000/health`；页面顶部显示 `API ONLINE` 后再进行公司、告警和证据联调。

## 数据边界

默认 Compose 配置使用 `synthetic_demo`，只用于联调。正式语料部署必须显式设置 `DATA_MODE=real_corpus` 和对应 `CORPUS_PATH`，不能把演示数据当作真实财务材料。
