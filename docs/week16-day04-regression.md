# Week 16 Day 4：v0.1 最终回归

## 自动化结果

| 范围 | 命令 | 结果 |
|---|---|---|
| 后端 | `python -m pytest -q` | **50 passed** |
| 前端单元测试 | `npm test` | **10 passed** |
| 前端类型检查 | `npx tsc --noEmit --pretty false` | **通过** |
| 前端生产构建 | `NEXT_PRIVATE_BUILD_WORKER=1; npm run build` | **通过** |

前端命令在沙箱外运行；沙箱内 Node 子进程会触发 Windows `spawn EPERM`。`NEXT_PRIVATE_BUILD_WORKER=1` 用于避免 Next.js worker 启动限制。

## 未完成的环境验收

- Podman machine 当前无法提供 compose 连接，容器端到端未测量。
- 浏览器视觉验收仍需人工执行。
- 真实 LLM provider 未配置，第十四周结果是确定性适配器对照。

详细机器可读结果见 `data/evals/week16-release-regression.json`。
