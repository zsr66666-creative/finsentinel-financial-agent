# Week 12 Day 5：部署与安全验收

## 完成内容

- API 响应增加 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY` 和 `Referrer-Policy: same-origin`。
- CORS 继续限制为 `CORS_ORIGINS` 配置的来源，默认只允许 `http://localhost:3000`。
- 增加安全头和跨域边界回归测试。
- 保持 `synthetic_demo`、`real_corpus` 和 `real_public_disclosure_local_copy` 数据模式标记，避免演示数据被误认为真实披露。

## 部署检查

```cmd
podman ps
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/observability
```

生产部署应显式设置 `DATA_MODE`、`DATABASE_URL`、`CORS_ORIGINS` 和 `CORPUS_PATH`，不得把密钥写入 Compose 文件或提交到仓库。

## 验证边界

本日完成的是应用层配置和自动化回归。实际 Podman 镜像构建仍取决于本机能否访问基础镜像仓库。
