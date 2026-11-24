# 经营现金流与净利润金融 Agent 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为五家试点公司实现可审计的经营现金流与净利润背离分析，包括核验数据契约、Decimal 公式、结构化结论、图表数据和前端展示。

**Architecture:** 保留现有 FastAPI + SQLite + Next.js 架构。后端新增经过来源绑定的财务输入与确定性分析服务；现有 Agent workflow 只负责问题规划和工具编排，公式、判定和图表数据由后端服务完成。前端消费结构化分析响应并展示公式、输入证据、页码和图表状态。

**Tech Stack:** Python 3.12、FastAPI、Pydantic、SQLite、Decimal、pytest、Next.js、React、Node test runner。

## Global Constraints

- 只有 `human_verified` 的财务输入可以进入正式结论。
- 所有金额必须带单位、合并报表口径、报告期、文档 SHA256、PDF 物理页码和原文片段。
- 计算使用 `Decimal`；上期为零、缺失、单位冲突或口径冲突必须返回 `needs_review`。
- LLM 不直接计算数值，也不能补齐缺失数据。
- 图表只能使用后端返回的真实计算结果，缺失年度保持为空。
- 不把合成 fixture、目标值或 RAG 通过状态写成真实财务分析通过。
- 保留用户现有未提交改动；每次提交只包含本任务相关文件。

---

### Task 1: 扩展财务输入与分析响应契约

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/store.py`
- Test: `backend/tests/test_financial_analysis_contract.py`

**Interfaces:**
- Produces `FinancialInput` 字段：`company_id`, `metric`, `period`, `value`, `unit`, `statement_scope`, `document_sha256`, `page`, `excerpt`, `extraction_status`, `evidence_id`。
- Produces `AnalysisResponse` 字段：`status`, `classification`, `metrics`, `charts`, `evidence`, `formula_version`。

- [ ] **Step 1: Write failing contract tests**

```python
def test_verified_input_requires_page_and_document_hash():
    with pytest.raises(ValidationError):
        FinancialInput(company_id="000100", metric="net_profit", period="2024FY",
                       value="1", unit="CNY", statement_scope="consolidated",
                       extraction_status="human_verified")

def test_needs_review_response_can_explain_missing_input():
    result = AnalysisResponse(status="needs_review", classification="无法判断",
                              metrics=[], charts=[], evidence=[],
                              reason="missing verified cash flow")
    assert result.status == "needs_review"
```

- [ ] **Step 2: Run `pytest backend/tests/test_financial_analysis_contract.py -q` and verify it fails before implementation.**
- [ ] **Step 3: Add typed Pydantic models and storage fields without changing existing fixture records.**
- [ ] **Step 4: Run the contract tests and the existing backend schema tests; expect all PASS.**
- [ ] **Step 5: Commit with `git add backend/app/schemas.py backend/app/store.py backend/tests/test_financial_analysis_contract.py; git commit -m "feat: add audited financial analysis contracts"`.**

### Task 2: Implement deterministic financial formulas and rule classification

**Files:**
- Create: `backend/app/financial_analysis.py`
- Test: `backend/tests/test_financial_analysis.py`

**Interfaces:**
- `calc_yoy(current: Decimal, previous: Decimal) -> Decimal`
- `calc_cash_profit_ratio(cash_flow: Decimal, net_profit: Decimal) -> Decimal`
- `classify_divergence(net_profit_yoy: Decimal, cash_flow_yoy: Decimal) -> str`
- `analyze_pair(net_profit_previous: FinancialInput, net_profit_current: FinancialInput, cash_previous: FinancialInput, cash_current: FinancialInput) -> AnalysisResult`

- [ ] **Step 1: Write tests for all four classifications, zero denominator, missing verification, unit mismatch, and negative prior values.**
- [ ] **Step 2: Run `pytest backend/tests/test_financial_analysis.py -q`; confirm the new tests fail.**
- [ ] **Step 3: Implement Decimal-only formulas, input validation, formula strings, input IDs and evidence IDs.**
- [ ] **Step 4: Run the tests; verify exact Decimal results and `needs_review` behavior.**
- [ ] **Step 5: Commit with `git add backend/app/financial_analysis.py backend/tests/test_financial_analysis.py; git commit -m "feat: calculate audited cash flow profit divergence"`.**

### Task 3: Connect verified report data and analysis API

**Files:**
- Modify: `backend/app/corpus.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/tools.py`
- Modify: `backend/app/workflow.py`
- Test: `backend/tests/test_financial_analysis_api.py`

**Interfaces:**
- `GET /api/v1/companies/{company_id}/financial-analysis?from_period=2023FY&to_period=2024FY`
- `POST /api/v1/analysis/runs` returns the same financial analysis fields when the question requests cash-flow/profit divergence.
- `Tools.analyze_cashflow_profit(company_id, periods) -> AnalysisResponse`
- `Tools.build_cashflow_profit_charts(company_id, periods) -> list[ChartSpec]`

- [ ] **Step 1: Add API tests using verified records and assert formulas, classification, evidence pages and chart values.**
- [ ] **Step 2: Run the API tests and confirm the endpoint is absent or incomplete.**
- [ ] **Step 3: Map ingested metric records to the audited input contract; reject records whose extraction status is not `human_verified`.**
- [ ] **Step 4: Add the analysis endpoint and route matching questions through the deterministic tool; keep generic RAG behavior unchanged.**
- [ ] **Step 5: Run backend regression tests and API tests.**
- [ ] **Step 6: Commit with `git add backend/app/corpus.py backend/app/main.py backend/app/tools.py backend/app/workflow.py backend/tests/test_financial_analysis_api.py; git commit -m "feat: expose audited cash flow analysis API"`.**

### Task 4: Add chart payloads and frontend financial analysis panels

**Files:**
- Modify: `frontend/src/lib/domain.mjs`
- Modify: `frontend/src/lib/domain.d.mts`
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/globals.css`
- Test: `frontend/tests/domain.test.mjs`

**Interfaces:**
- `normalizeFinancialAnalysis(payload)` preserves `status`, `classification`, `metrics`, `charts`, `evidence`, and `reason`.
- UI renders a formula table, evidence links with physical pages, a two-series yoy chart, and a cash-profit-ratio trend chart.

- [ ] **Step 1: Add domain tests for complete results, `needs_review`, missing years, zero values and source page preservation.**
- [ ] **Step 2: Run `npm test --prefix frontend`; confirm the new assertions fail.**
- [ ] **Step 3: Implement normalization and render panels using returned data only; show “需复核” when status is not `completed`.**
- [ ] **Step 4: Add accessible SVG or existing chart component with labels, units, missing-value markers and source-page links.**
- [ ] **Step 5: Run frontend tests, TypeScript check and production build.**
- [ ] **Step 6: Commit with `git add frontend/src/lib/domain.mjs frontend/src/lib/domain.d.mts frontend/src/app/page.tsx frontend/src/app/globals.css frontend/tests/domain.test.mjs; git commit -m "feat: show audited financial charts and conclusions"`.**

### Task 5: Build five-company verified fixtures and acceptance checks

**Files:**
- Create: `backend/tests/fixtures/financial_analysis_verified.json`
- Create: `backend/tests/test_five_company_financial_acceptance.py`
- Create: `scripts/verify_financial_analysis.py`
- Modify: `docs/week15-browser-acceptance-checklist.md`

**Interfaces:**
- Fixture covers `000100`, `000157`, `000425`, `000528`, `000725` with adjacent verified periods and page/evidence metadata.
- Script exits nonzero if any company lacks formula, evidence page, chart parity or valid classification.

- [ ] **Step 1: Add fixtures using only audited values and recorded evidence metadata; never copy synthetic seed values.**
- [ ] **Step 2: Write acceptance tests for five companies, Decimal recomputation, evidence coverage, chart parity and needs-review fallback.**
- [ ] **Step 3: Run the acceptance tests and verify the script initially rejects incomplete fixtures.**
- [ ] **Step 4: Complete the verified fixture mapping and make the script pass.**
- [ ] **Step 5: Run `python scripts/verify_financial_analysis.py`; record company-by-company PASS output.**
- [ ] **Step 6: Commit with `git add backend/tests/fixtures/financial_analysis_verified.json backend/tests/test_five_company_financial_acceptance.py scripts/verify_financial_analysis.py docs/week15-browser-acceptance-checklist.md; git commit -m "test: add five-company financial analysis acceptance"`.**

### Task 6: Update README, run full verification, and prepare main delivery

**Files:**
- Modify: `README.md`
- Create: `docs/financial-analysis-acceptance.md`

- [ ] **Step 1: Document formulas, verified-data requirement, API endpoint, local acceptance commands and known limits.**
- [ ] **Step 2: Run backend tests, frontend tests, TypeScript check, production build and the five-company acceptance script.**
- [ ] **Step 3: Inspect `git diff --check`, `git status`, active branch and remote; verify no unrelated user changes are staged.**
- [ ] **Step 4: Commit README and acceptance report.**
- [ ] **Step 5: Merge the feature branch into `main` only after all verification output is recorded.**
- [ ] **Step 6: Push `main` to `origin` and report the commit SHA, test outputs, deployment status and any remaining WARN items.**

## Verification Commands

```powershell
pytest backend/tests -q
npm test --prefix frontend
npx --prefix frontend tsc --noEmit
npm run build --prefix frontend
python scripts/verify_financial_analysis.py
git diff --check
```

The final report must separate local tests, deployed-service checks, and browser/manual acceptance. A passing RAG retrieval screenshot alone does not count as financial calculation acceptance.
