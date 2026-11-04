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
