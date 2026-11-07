# Week 16 Day 6：v0.1 发布冻结检查

## 当前状态

| 项目 | 状态 | 证据 |
|---|---|---|
| 工作区无业务修改 | PASS | `git status --short --branch` 仅显示 `main...origin/main` |
| 本地与远程同步 | PASS | `origin/main` 已由推送脚本核对 |
| 后端回归 | PASS | 50 passed |
| 前端测试 | PASS | 10 passed |
| 前端类型检查 | PASS | `npx tsc --noEmit --pretty false` |
| 前端构建 | PASS | `NEXT_PRIVATE_BUILD_WORKER=1; npm run build` |
| CI 远程运行 | PENDING | 需在 GitHub Actions 页面确认 workflow run |
| Compose 端到端 | BLOCKED | Podman machine 连接不可用 |
| 浏览器视觉验收 | MANUAL | 需人工按 checklist 执行 |

## 发布结论

代码和文档达到 v0.1.0-rc1 候选状态。正式打 tag 前，应确认 GitHub Actions run 为绿色，并在有可用容器运行时的环境完成 Compose 健康检查。上述两项未完成前，不宣称生产部署已验证。

## 冻结范围

冻结后只接受影响正确性、安全性或可复现启动的修复；新功能进入 v0.2 计划。合成演示、真实语料和确定性 Agent 对照继续分开记录。
