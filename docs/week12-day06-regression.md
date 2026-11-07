# Week 12 Day 6：发布回归验收

## 已验证

- Python 应用编译通过。
- 安全响应头和 CORS 边界冒烟测试通过。
- 前端测试和生产构建在 Day 5 基线中已通过：9 项测试，构建成功。
- Day 12 API、观测和安全测试代码已纳入后端回归集。

## 环境记录

本机 Windows pytest 运行过程中，历史 `.pytest-tmp` 和临时目录被系统拒绝清理，出现 `WinError 5`。输出中的业务断言已执行，但 pytest 在会话清理阶段异常退出。该问题属于测试临时目录权限，不是 API 断言失败；需要在本机清理受保护的临时目录后重新取得完整退出码。

## 发布检查

- Git 工作区不提交 PDF、数据库、`.next` 或 pytest 临时目录。
- 默认 Compose 模式为 `synthetic_demo`。
- 真实语料部署必须显式配置 `DATA_MODE=real_corpus` 和 `CORPUS_PATH`。
