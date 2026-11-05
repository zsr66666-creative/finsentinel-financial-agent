# Week 09 证据来源与评测加固实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将前八周的真实来源、公告证据和评测流程整理为可复核、可重复运行的第九周交付物。

**Architecture:** 保留当前 FastAPI、SQLite、BM25 和 JSONL 评测边界。第九周只加强来源元数据、公告证据映射、评测报告和测试运行环境，不引入大模型或自动投资建议。

**Tech Stack:** Python 3.12, pytest, SQLite, JSON/JSONL/CSV, Git。

## Global Constraints

- 原始 PDF 不提交 Git；只提交来源 URL、SHA-256、页数和解析元数据。
- 未核验的 URL 必须标记为 `pending_document_mapping`，不得绑定到猜测的文档。
- 所有金额保留原始单位和字符串精度；派生值必须记录公式和证据 ID。
- Recall@5 必须区分 development 与冻结 test，不能用 test 集调参。
- 不输出股价预测、自动交易或投资建议。

---

### Task 1: 清理并验证工作区

**Files:**
- Modify: `backend/pytest.ini`（如不存在则创建）
- Modify: `.gitignore`
- Test: `backend/tests/`

- [ ] **Step 1: 固定 pytest 临时目录**

在 `backend/pytest.ini` 写入：

```ini
[pytest]
testpaths = tests
addopts = -q
basetemp = .tmp/pytest
```

- [ ] **Step 2: 忽略运行时目录**

在 `.gitignore` 保留：

```gitignore
backend/.tmp/
backend/*.db
backend/data/
```

- [ ] **Step 3: 从仓库根目录运行测试**

运行：`python -m pytest backend/tests -q`

预期：不再出现 `C:\Users\...\pytest-of-...` 权限错误；若仍有失败，只记录真实代码失败。

- [ ] **Step 4: 提交**

```bash
git add backend/pytest.ini .gitignore
git commit -m "test: isolate pytest temporary files"
```

### Task 2: 核验官方来源映射

**Files:**
- Modify: `data/manifests/official_urls.csv`
- Modify: `data/manifests/lixun-corpus-manifest.json`
- Modify: `data/derived/documents/*.json`
- Test: `backend/tests/test_ingestion_pipeline.py`

- [ ] **Step 1: 对每个 `szse-001` 至 `szse-008` 记录页面标题、证券代码、披露日期和附件 PDF 文件名**
- [ ] **Step 2: 只有附件与已有 `document_id`、SHA-256、页数全部一致时，才将状态改为 `verified`**
- [ ] **Step 3: 对无法核验的链接保留 `pending_document_mapping`，并填写阻塞原因**
- [ ] **Step 4: 运行 `python -m pytest backend/tests/test_ingestion_pipeline.py -q`**
- [ ] **Step 5: 提交**

```bash
git add data/manifests data/derived/documents
git commit -m "data: verify official disclosure mappings"
```

### Task 3: 完善公告事件证据

**Files:**
- Modify: `data/derived/documents/*.json`
- Modify: `data/evals/golden_questions.jsonl`
- Create: `data/evals/event-evidence-week09.jsonl`
- Test: `backend/tests/test_event_rules.py`

- [ ] **Step 1: 为减值、诉讼、重大客户、关联交易、回购和担保事件各保留一条原文证据**
- [ ] **Step 2: 每条证据写入 `document_id`、页码或 span、原文片段、事件类型和人工核验状态**
- [ ] **Step 3: 为新增公司事件题补齐 `gold_evidence_ids`，不把制度文件误标为事件公告**
- [ ] **Step 4: 运行 `python -m pytest backend/tests/test_event_rules.py -q`**
- [ ] **Step 5: 提交**

```bash
git add data/derived/documents data/evals
git commit -m "eval: add audited event evidence"
```

### Task 4: 生成第九周评测报告

**Files:**
- Create: `data/evals/retrieval-run-week09.json`
- Create: `docs/week09-evaluation-report.md`
- Test: `backend/tests/test_week7_8_retrieval_eval.py`

- [ ] **Step 1: 只使用 development 题调参，固定 test 题**
- [ ] **Step 2: 按公司、题型和数据集划分统计 Recall@5、证据支持率和正确拒答率**
- [ ] **Step 3: 报告每个分母和分子，并注明语料版本、代码版本和运行时间**
- [ ] **Step 4: 运行 `python -m pytest backend/tests/test_week7_8_retrieval_eval.py -q`**
- [ ] **Step 5: 提交**

```bash
git add data/evals/retrieval-run-week09.json docs/week09-evaluation-report.md
git commit -m "eval: publish week nine retrieval report"
```

### Task 5: 发布前检查

**Files:**
- Modify: `docs/docsweek-01-report.md`
- Modify: `progress.md`

- [ ] **Step 1: 检查 `git status --short`，确认没有数据库、PDF 或临时目录**
- [ ] **Step 2: 运行完整测试：`python -m pytest backend/tests -q`**
- [ ] **Step 3: 检查 17 份材料、5 家公司、48 条黄金问题和所有评测快照的计数**
- [ ] **Step 4: 将未完成来源映射和测试环境限制写入周报**
- [ ] **Step 5: 提交并推送 `main`**

```bash
git add docs progress.md
git commit -m "docs: close week eight and start week nine"
git push origin main
```
