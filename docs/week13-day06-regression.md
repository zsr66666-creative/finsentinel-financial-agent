# 第十三周 Day 6：回归检查

## 后端

命令：`python -m pytest backend/tests -q`

结果：46 项测试通过，未再出现 Windows pytest 临时目录 `WinError 5`。

## 前端

`npm test -- --runInBand` 和 `npm run build` 在当前 Codex Windows 沙箱中均被 Node 子进程权限阻止：

```text
Error: spawn EPERM
```

该错误发生在 Node/Next 启动子进程阶段，不是 TypeScript、组件断言或构建错误。需要在本机 CMD/PowerShell 或解除 Node 子进程限制的环境中复跑。

## 代码检查

`git diff --check` 通过内容检查；历史受保护 pytest 目录仍被忽略，不参与新测试。

## 前端沙箱问题复核（2026-11-07）

通过在 Codex 沙箱外获准运行 npm 命令，确认之前的 `spawn EPERM` 是沙箱对 Node worker 子进程的限制，不是项目代码或 Node 测试本身错误。

- `npm test`：9 passed；
- `npm run build`：Next.js 生产构建成功；
- 未保留 `next.config.mjs` 的 worker 数量试验改动。

后续在 Codex 中运行前端测试/构建时应使用沙箱外授权执行。若在用户本机终端运行，则直接进入 `frontend` 目录执行 `npm test` 和 `npm run build`。
