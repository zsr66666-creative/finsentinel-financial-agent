# 第九周 Day 7 冻结记录

日期：2026-11-06

## 已完成

- 第九周 Day 1–Day 6 的数据、证据、测试和评测报告已提交。
- 当前评测报告：`docs/week09-evaluation-report.md`。
- 当前评测明细：`data/evals/retrieval-run-week09.json`。
- 当前代码版本：`cdd9a6d`（第九周评测报告提交）。
- `git diff --check` 通过。
- 未发现新增未跟踪的业务源 PDF、SQLite 数据库或 `.browser-config`；`.browser-config`、仓库根目录 `.pytest-tmp` 和 `.tmp` 已清理。

## 评测冻结值

- 全部：9 / 48 命中，Recall@5 = 0.5294（17 条可评分题）。
- development：7 / 36 命中，Recall@5 = 0.5385（13 条可评分题）。
- test：2 / 12 命中，Recall@5 = 0.5000（4 条可评分题）。
- 语料版本：`week8-multi-company-v2`。
- 检索模式：`bm25_only`，Top-K = 5，未配置向量嵌入。

## 环境收尾限制

部分由 Windows 测试运行产生的临时目录仍被当前 Codex 沙箱拒绝访问，包括 `backend/.pytest_cache`、`backend/.tmp`、`backend/pytest-cache-files-*` 和根目录下的历史 pytest 临时目录。它们均为被 `.gitignore` 忽略的运行产物，不影响 Git 提交，也没有被纳入版本库。若要完全删除，请在本机 CMD 关闭正在运行的 pytest 进程后清理这些目录。

## Git 状态

Day 7 记录提交后，应保持工作区无业务文件修改；由于当前 Codex 环境无法使用 GitHub HTTPS 凭据，推送需在用户本机 CMD 执行 `git push origin main`。
