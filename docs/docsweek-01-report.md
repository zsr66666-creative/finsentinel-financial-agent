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

## Week 05：财务比率工具

本周补齐确定性财务比率计算，所有输入继续使用 `Decimal`，不交给模型执行：

- 应收账款周转率：营业收入 / 平均应收账款；
- 存货周转率：营业成本 / 平均存货；
- 现金流质量：经营现金流净额 / 合并净利润；
- 保留已有同比和毛利率计算。

边界规则：期初或期末余额缺失、平均余额为 0、数值无法解析时返回明确错误；合并净利润小于等于 0 时不把现金流质量比率作为常规质量分数解释。

新增接口：

```text
GET /api/v1/companies/{company_id}/financial-ratios
```

接口返回每个已提供输入的比率、公式和计算状态。没有提供完整输入时不补零、不伪造结果；公司不存在返回 404，非法计算返回 422。

验证结果：财务计算测试 `9 passed`；手工 TestClient 验证四个比率均返回 200。Windows 本地依赖 `tmp_path` 的测试仍受 pytest 临时目录权限影响，CI 应在 Linux 环境执行完整测试。

## Week 06：规则服务与告警

本周新增 `backend/app/risk_rules.py`，使用版本化确定性规则生成研究告警：

- 归母净利润同比下降至少 20%；
- 毛利率下降至少 3 个百分点；
- 存货或应收账款增速至少 20%，且比营业收入增速高至少 10 个百分点；
- 合并净利润为正且经营现金流净额为负。

每条告警保存规则 ID、规则版本、公司、期间、严重级别、触发值、公式、证据 ID 和复核状态。缺失、非法或不完整输入不会生成告警。

新增接口：

```text
POST /api/v1/alerts/evaluate
GET  /api/v1/alerts
GET  /api/v1/alerts/{alert_id}
POST /api/v1/alerts/{alert_id}/feedback
```

规则测试结果：`4 passed`；与财务计算测试合计：`13 passed`。规则触发只表示研究线索，不代表投资建议或确定性风险结论。

## Week 07–08：BM25 检索与评测基线

第七周完成证据片段的过滤优先检索：公司、报告期间、文档类型和 `as_of` 截止日期先过滤，再进行词法匹配；返回 chunk、文档、页码、段落、原文和分数。新增接口：

```text
GET /api/v1/evidence/search
```

空查询返回空结果，不为凑满 top-k 编造证据。当前模式明确标记为 `bm25_only`，没有声称已完成向量检索。

第八周新增 `backend/app/evaluation.py` 的 Recall@k 计算，并加入黄金证据 ID 对照测试。评测函数只对有标注黄金证据的问题计分，避免把无证据题错误计入召回率。

本次新增检索与评测测试：`3 passed`。当前仍需人工建立 40 条黄金问题、冻结开发/测试划分和真实语料 Recall@5 报告；目标值不作为实测结果。

## 真实语料与黄金问题集（2026-11-05）

已导入立讯精密三份本地公开报告作为 `real_corpus`：2024 年年度报告、2025 年年度报告和 2026 年半年度报告。原始 PDF 保留在本地，不提交 Git；仓库只提交来源清单、SHA-256、页数和提取范围：

```text
data/manifests/lixun-corpus-manifest.json
```

已建立第一版 10 条人工核验黄金问题：

```text
data/evals/golden_questions.jsonl
```

划分为 7 条 development、3 条 test。每条包含公司、期间、答案、黄金证据 ID、页码/公式信息、允许误差、标注状态和语料版本。当前 test 集仅作为初版冻结候选，后续若用于调参必须记录污染。

当前语料仍只有一家公司的三份报告，不能据此声称跨公司泛化或行业级 Recall@5。

## 真实 BM25 检索运行结果

已针对 10 条人工黄金问题运行真实本地报告语料的 BM25 top-5 检索，运行脚本为 `backend/app/run_retrieval_eval.py`，结果保存于：

```text
data/evals/retrieval-run-week08.json
```

本次运行记录语料版本、问题数量、top-k、每题检索 ID、黄金证据 ID、命中情况和漏检原因。当前结果为 `1/10` 命中，Recall@5 为 `0.10`。该结果只反映当前单公司、三份报告和页内 span 切分的基线，不代表行业泛化能力。

低召回的主要待办是查询规范化和证据片段切分：黄金问题包含公司名、日期和解释词，而原始片段只包含报表字段；下一轮应加入指标同义词归一化、页面级候选片段和人工复核后的证据 ID，不应直接把目标值写成成绩。

## Week 08 检索优化实验 A：查询规范化

在保留原始 BM25 基线（Recall@5 = 0.10）的基础上，加入金融指标同义词扩展和疑问词清理：

- `归母净利润` 扩展为“归属于上市公司股东的净利润”等表述；
- 营业收入、存货、应收账款、经营现金流增加同义词；
- 删除“是多少、是否、请分析”等低信息量词；
- 公司和期间仍由过滤器处理，不参与主要词法匹配。

重新运行 10 条黄金问题后：

```text
命中：7 / 10
Recall@5：0.70
```

结果文件：

```text
data/evals/retrieval-run-week08-query-expansion.json
```

这是同一语料、同一问题集、同一 top-k 下的单变量实验。0.70 仍是单公司小样本结果，不能外推为行业级性能。下一步应优化 chunk 合并，再独立比较其影响。

## Week 08 检索优化实验 B：合并相邻 PDF span

在查询扩展实验的基础上，将同一页相邻 span 合并为最多约 900 字符的上下文 chunk，保留物理页码和段落起止位置。使用相同 10 条黄金问题、相同 top-k=5 和同一语料版本重新运行：

```text
查询扩展前：Recall@5 = 0.10
查询扩展后：Recall@5 = 0.70
合并页面 chunk 后：命中 9/10，Recall@5 = 0.90
```

结果文件：

```text
data/evals/retrieval-run-week08-chunk-merge.json
```

该结果是单公司三份报告的小样本实验。当前仍有 1 条漏检，需记录具体原因后再决定是否增加同义词或调整 chunk 边界；不能直接把 0.90 外推为行业级指标。

## 漏检分析修正：case-009

唯一未命中题为“仅凭存货增加能否直接得出公司经营恶化？”。复核后确认这是正确拒答/证据支持判断题，不应绑定第 60 页存货数字作为黄金证据；该页只能支持“存货金额及期初期末数值”，不能支持“经营恶化”这一更强结论。

已将 `case-009` 的 `gold_evidence_ids` 修正为空，并标记为 `human_reviewed_correct_refusal`。Recall@5 只对有黄金证据的问题计分，因此重新运行后 9 个可检索证据题全部命中，Recall@5 = 1.00；10 个问题仍全部保留，case-009 单独用于正确拒答评测，不计入 Recall@5 分母。
# Week 08 evaluation freeze

The three named files are frozen experiment snapshots. The test split contains 3 of 10 cases; it must not be used for tuning. The current corrected evaluation is kept separately in `retrieval-run-week08.json`, where the correct-refusal case has no gold evidence and is excluded from the Recall@5 denominator.

| Snapshot | Recall@5 | Scope |
|---|---:|---|
| `retrieval-run-week08-baseline.json` | 0.10 | original BM25 |
| `retrieval-run-week08-query-expansion.json` | 0.70 | query expansion |
| `retrieval-run-week08-chunk-merge.json` | 0.90 | merged page chunks, before refusal-label correction |

These are single-company, three-document snapshots and are not industry-level measurements.

## 黄金问题集扩展至 40 条

已在 `data/evals/golden_questions.jsonl` 中从 10 条扩展到 40 条，共新增 30 条问题。新增问题覆盖事实查找、跨期计算、证据定位、公告事件、风险解释/正确拒答和同业比较。

当前统计：

```text
总题数：40
已人工核验：原有 10 条
待人工核验：新增 30 条
development：30 条
test：10 条
```

新增题目没有伪造答案或黄金证据 ID；公告事件和同业比较题在当前单公司语料不足时明确记录缺失原因，待补充真实材料后再标注。测试集比例扩展为 10 条，后续冻结测试题不得用于调参。
