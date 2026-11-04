# Week 01：第一条财务数据链路

## 本周目标

完成一条真实财务指标从数据库、后端 API 到前端页面的闭环。

## 首家公司

- 公司：立讯精密
- 股票代码：002475
- 交易所：深圳证券交易所
- 行业：消费电子/电子制造

## 首版指标

- 营业收入
- 归母净利润
- 存货

## 本周不做

- 大模型
- LangChain
- LangGraph
- RAG
- 多 Agent
- 向量数据库
- 自动 PDF 解析
- 股价预测和自动交易

## Day 2：真实报告与首批指标记录

### 已处理文件

- 文件：立讯精密：2026年半年度报告.PDF
- 页数：233
- 文件大小：3,812,196 bytes
- SHA-256：`841a3271cddd0e0e6bf9d60e39bda69fa48de13c67300c313395d849bddfa588`
- 访问/记录时间：2026-11-04 11:43:54 UTC
- 解析方式：PyMuPDF 文本提取后人工核对页码

### 首批指标

| 指标 | 期间 | 原始值 | 单位 | 报表口径 | PDF 页码 |
|---|---|---:|---|---|---:|
| 营业收入 | 2026H1 | 174,504,335,921.25 | 元 | 合并 | 8 |
| 归属于上市公司股东的净利润 | 2026H1 | 7,842,698,288.86 | 元 | 合并 | 8 |
| 存货 | 2026-06-30 | 50,367,311,994.53 | 元 | 合并 | 60 |

详细结构化记录见 [`data/examples/first-company-metrics.json`](../data/examples/first-company-metrics.json)。

### 数据边界

用户提供的是 2026 年半年度报告，不是原计划建议的 2024 年年度报告，因此本次记录使用 `2026H1` 和 `2026-06-30`。不能把它与年度数据直接做年度同比。PDF 本身没有精确官方公告 URL，`source_url` 暂留空，需从巨潮资讯或公司官网补录后再作为公开语料来源。

## Day 3：第一版数据库字段与数据口径

已确定 v0.1 的四张核心表和关系：

```text
companies 1 ─── * documents 1 ─── * evidence_spans
companies 1 ─── * financial_metrics * ─── 1 documents
```

已写入 [`docs/data-contract.md`](data-contract.md)，重点规则包括：

- 报告期间、披露日期和实际获取时间分开保存；
- 金额保留原始值和原始单位，不能把“千元”默认为“元”；
- 归母净利润使用独立指标名，不能与合并净利润混用；
- 缺失值使用 `NULL` 并记录原因，不能用 0 代替；
- 每个指标必须关联来源文档、物理页码和证据片段；
- `(company_id, sha256)` 用于文档去重和重复导入幂等；
- `2026H1` 不得标记为 `2026FY`，不同报告期间不能直接比较。

Day 3 的完成标准已达到：数据库模型可以据此实现，后端 API 可以据此设计，前端可以据此显示数值、单位、期间和来源。

## Day 4：建立 SQLite 数据库

已完成 SQLite 本地数据库初始化层：

- `backend/app/database.py`：默认 `sqlite:///./finsentinel.db`，并开启 SQLite 外键检查；
- `backend/app/models.py`：公司、文档、指标和证据的 Pydantic 数据模型；
- `backend/app/seed.py`：从 `data/examples/first-company-metrics.json` 建立第一周真实样本；
- `backend/app/check_database.py`：检查数据库记录数量、关联来源和基本数据完整性。

运行命令：

```powershell
cd backend
$env:PYTHONPATH = "."
python -m app.seed
python -m app.check_database
```

实际检查结果：

```text
companies: 1
filings: 1
financial_metrics: 3
evidence_spans: 3
```

当前三项指标仍保留原始“元”单位、报告期间和来源证据 ID。重复执行 `python -m app.seed` 会先重建 Day 4 本地样本，不会累加重复记录；后续导入器需要将同样的幂等规则迁移到正式 Alembic 数据库模型。

## Day 5：FastAPI 指标与证据接口

已实现并验证：

```text
GET /api/v1/companies
GET /api/v1/companies/{company_id}/metrics
GET /api/v1/evidence/{evidence_id}
```

指标列表返回 `items`、`total`，每条指标补充公司名称、来源页码、来源 URL、报告期间、单位和 `data_mode`。证据接口返回文档 ID、物理 PDF 页码、原文片段、来源 URL和期间。

错误行为：

```text
不存在的公司 → 404
不存在的期间/指标 → 404
不存在的证据 → 404
```

实际 TestClient 检查结果：

```text
companies 200 24
metrics 200 12
missing_company 404
missing_metric 404
missing_evidence 404
```

当前默认 `create_app()` 使用 `synthetic_demo`，因此上面的 24 家公司和 12 条指标属于教学演示数据。Day 4 的 `seed_day4()` 仍用于本地真实报告三指标样本；启动真实资料 API 时需使用独立 SQLite 数据库和 `DATA_MODE=real_corpus`，避免将演示数据混入真实结果。

## Day 6：确定性财务计算与增长接口

本日目标是先完成可审计的财务计算基础，不引入大模型、LangChain、LangGraph、RAG 或多 Agent。

已完成：

- `backend/app/financial_calculations.py`：使用 `Decimal` 计算同比增长和毛利率，避免金额先转 `float` 造成精度损失；
- 对缺失值、基期为 0、基期为负数和收入为 0 的情况显式报错；
- `backend/tests/test_financial_calculations.py`：覆盖增长、下降、边界和毛利率场景；
- `GET /api/v1/companies/{company_id}/metrics/{metric}/growth`：返回当前值、上期值、增长结果、公式、来源 ID 和数据模式；
- `seed_day4()` 支持把真实样本中的 `comparatives` 写入上期指标；
- 立讯精密 2026H1 与 2025H1 的营业收入、归母净利润可进行同比计算；存货仍是资产负债表时点值，没有虚构同比数据。

验证命令：

```powershell
cd backend
$env:PYTHONPATH = "."
python -m pytest tests/test_financial_calculations.py -q
```

验证结果：

```text
5 passed in 0.01s
```

真实样本接口验证（`sqlite:///day6-real.db`，`data_mode=real_corpus`）：

```text
revenue 2026H1 vs 2025H1 → 200，增长 40.16%
net_profit_attributable 2026H1 vs 2025H1 → 200，增长 18.04%
inventory 缺少可比期间 → 404，不生成假数据
```

增长公式为：

```text
(current_value - previous_value) / previous_value × 100
```

本日结果仅代表当前本地真实公开披露样本的计算结果，不构成投资建议；简历中的性能和准确率指标仍需后续评测后填写。

## Day 7：第一周验收与可复现收尾

本日完成第一周收尾：

- 补充后端 README 中的增长接口契约、错误边界和真实数据模式说明；
- 增加增长 API 回归测试，确认营业收入同比为 `40.16%`，存货缺少可比期间时返回 `404`；
- 补齐确定性检索适配器 `backend/app/retrieval.py`，支持 BM25 结果、可选 embedding 接口、RRF 工具和 embedding 失败降级；
- 检索和财务计算 focused tests 共 `11 passed`。

验收命令：

```powershell
cd backend
$env:PYTHONPATH = "."
python -m pytest tests/test_financial_calculations.py tests/test_retrieval.py -q
```

当前 Windows 环境的 pytest 临时目录权限会影响依赖 `tmp_path` 的全量测试；这属于测试环境权限问题，已使用仓库目录下的 focused tests 完成 Day 7 核心验收。后续 CI 在 Linux runner 上执行完整测试集。

第一周最终闭环：真实指标样本 → SQLite → FastAPI → 精确计算 → 检索适配器 → 测试与周报。下一阶段再接入正式文档解析和工作流编排。

## 第一周完整验收日志

验收日期：2026-11-04

| 项目 | 结果 | 证据 |
|---|---|---|
| 首家公司与三项指标 | PASS | 立讯精密 002475；营业收入、归母净利润、存货 |
| SQLite 数据库 | PASS | `python -m app.seed` 成功；公司 1、年报 1、指标 5（含两个可比期间）、证据 3 |
| 数据库检查脚本 | PASS | 已兼容当前可比期间扩展，确认至少 3 个指标及来源关联 |
| FastAPI 基础接口 | PASS | 公司、指标、证据接口及 404 行为已在 Day 5 验证 |
| 确定性计算 | PASS | `Decimal` 同比、毛利率及边界测试 |
| 增长 API | PASS | 营业收入 40.16%，归母净利润 18.04%；存货缺少期间时 404 |
| 证据检索 | PASS | BM25、可选 embedding、RRF 和降级测试 |
| focused tests | PASS | `11 passed in 0.01s` |
| 开源文档 | PASS | README、架构、数据契约、评测说明和周报已提交 |

未纳入第一周的内容：大模型、LangChain、LangGraph、RAG、向量数据库、自动 PDF 解析和投资建议。全量测试仍受本机 Windows pytest 临时目录权限影响，已明确记录，后续 CI 负责完整环境验收。
