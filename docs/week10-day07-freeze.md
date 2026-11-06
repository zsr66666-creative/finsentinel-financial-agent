# 第十周 Day 7 冻结记录

日期：2026-11-06

## 第十周交付物

- Day 1 基线：`data/evals/retrieval-run-week10-baseline.json`、`docs/week10-day01-baseline.md`
- Day 2 黄金问题扩展：`data/evals/golden_questions.jsonl`、`docs/week10-day02-golden-expansion.md`
- Day 3 公告事件与风险证据：`data/evals/event-evidence-week10.jsonl`、`docs/week10-day03-event-risk.md`
- Day 4 检索策略对照：三个 `retrieval-run-week10-*.json` 实验文件
- Day 5 消融与向量状态：`data/evals/retrieval-run-week10-ablation.json`、`docs/week10-day05-retrieval-ablation.md`
- Day 6 正式评测：`data/evals/retrieval-run-week10.json`、`docs/week10-evaluation-report.md`

## 冻结评测结果

- 黄金问题：74 条。
- 可评分题：43 条。
- 当前最佳策略：BM25 + 查询扩展。
- Recall@5：34 / 74，结果为 0.7907。
- Recall@10：35 / 74，结果为 0.8140。
- 向量嵌入：未配置，未伪造向量检索结果。
- 语料版本：`week10-multi-company-v3`。

## 测试与质量检查

- 完整后端测试：48 passed。
- `git diff --check`：通过。
- JSON 评测文件：已解析并校验关键统计。
- 本次 Day 7 pytest 临时目录已尝试清理；Windows 沙箱可能保留历史 pytest 临时目录，它们被 `.gitignore` 忽略。

## 已知限制

- 当前向量检索和 BM25+向量混合检索尚未运行，因为环境没有真实 embedding provider。
- 第十周新增黄金问题全部进入 `development`；原有 `test` 集保持隔离。

## 代码版本

冻结记录提交前以 Git HEAD 为准；推送后通过 `main...origin/main` 验证远程同步。
