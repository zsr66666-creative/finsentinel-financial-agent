# Task 11: official-report financial comparison

## Scope and financial semantics

Two fixed official 2024FY PDFs already acquired in Task10; three consolidated metrics each. This is a fixed deterministic source contract, not arbitrary extraction or an independently human-adjudicated dataset. `supported` means the pinned original supports the numeric comparison; `review_status=pending_human` always remains explicit. No new risk conclusions.

| Company | Metric | Current CNY | Comparison CNY | Row physical page |
|---|---|---:|---:|---:|
| 002555 三七互娱 | 营业收入 | 17,440,957,495.58 | 16,546,871,737.85 | 92 |
| 002555 三七互娱 | 应收账款 | 1,212,667,677.20 | 1,479,267,695.67 | 88 |
| 002555 三七互娱 | 经营活动产生的现金流量净额 | 2,997,982,682.73 | 3,147,037,336.46 | 95 |
| 002230 科大讯飞 | 营业收入 | 23,343,093,018.69 | 19,650,329,209.04 | 119 |
| 002230 科大讯飞 | 应收账款 | 14,666,453,043.92 | 12,165,102,111.50 | 115 |
| 002230 科大讯飞 | 经营活动产生的现金流量净额 | 2,495,173,454.92 | 349,757,814.55 | 123 |

Revenue and cash flow compare 2024-01-01/2024-12-31 against 2023-01-01/2023-12-31. Receivables compare closing and opening balances: 002230 explicitly labels 2024-12-31 and 2024-01-01, while 002555 uses 期末余额 / 期初余额 under a 2024-12-31 heading. We preserve `opening_balance_2024` for the latter and do not invent a printed 2023-12-31 date.

Amounts stay decimal strings in CNY. Difference=current−comparison; percentage=(current−comparison)/abs(comparison)*100, half-up to two decimal places. Zero comparison gives null percentage with `zero_comparison_base`; negative bases use absolute denominator. Up/down is descriptive, not a risk score. No floating-point amount formatting in frontend.

## Read-only evidence contract

`backend/app/data/task11-financial-contracts.json` holds six source contracts. A response requires an existing committed ingestion artifact matching ID/company/year/type/SHA256, its local PDF under the configured root, full byte hash, correct total pages, normalized page hashes and exact table-title/unit/period/row excerpts. Fixed statement semantics additionally bind returned labels, columns and period metadata. Continuations may span at most adjacent pages. Proofs expose physical page, excerpt, text hashes and normalized character offsets; proof IDs are contract locators, not vector chunk IDs.

Some statement pages are outside Task10's selected search index. Direct PDF contract validation does not expand search coverage or vector counts. This feature writes neither index rows nor financial-metric/demo records. No new migration, model or runtime dependency. PyMuPDF minor versions that change normalized extraction fail closed and need source investigation, never a silent numerical fallback.

## API and UI

GET `/api/v1/companies/002555/financial-comparison?period=2024FY&statement_scope=consolidated`

Also supported for 002230. Unknown company/period/scope => HTTP200 `needs_review`, empty items. Missing or mismatched artifact/PDF/page proof => `needs_review` items without monetary fields; operational SQL/manifest failure => HTTP503. Existing `/metrics`, original `/api/v1/evidence/compare` and source-search APIs retain behavior. `INGESTION_ARTIFACT_ROOT` defaults to `/var/lib/finsentinel/ingestion`.

Company pages add a separate financial comparison panel with three statement rows, exact values, raw periods, difference/percentage, original PDF links and pending-human-review label. Selecting the uncovered parent scope clears amounts and explains missing coverage. Data mode remains separate from demo monitoring. No redesign of existing macOS chrome, theme or navigation.

## Deployment and rollback

Precondition: Task10 fully deployed, two original PDFs and committed artifacts retained, backend/frontend/query encoder/ingestion active, standalone frontend layout, at least700MiB available. Upload the source-only archive to `/root/`, validate SHA256, extract into a fresh directory and invoke `deploy/ecs/install-task11-offline.sh`. The wrapper syntax-checks the shared installer before execution.

Build (`npm ci`, `npm test`, `npm run build`) while old site serves. Preserve old hashed assets and standalone static/public directories; dump PG before switching. Source-only six-metric acceptance runs on staged backend before any service switch. Update the existing90-task9-corpus backend drop-in with prior backup; direct API acceptance precedes frontend switch, then Nginx page/assets/API acceptance. Re-run Task10/Task9 retrieval and original reviewed comparison. Task11 skips acquisition, vector encoding and vector publication, and keeps the encoder running.

Any switch failure restores prior backend drop-in and frontend build and restarts services; production DB is never automatically overwritten. Release/backup and acceptance JSON stay under `/opt/finsentinel-releases/task11-corpus-*`. Existing service environment supplies DB connection. Nginx and external port policy unchanged. Source package includes no PDF/model/database/secrets; no GitHub access required on ECS beyond ordinary npm installation.

## Measured local validation and remaining gates

- 9 targeted Task11 backend tests pass, including actual official PDFs and48 metadata mutation checks. Broader backend regression:68 collected,66 passed,2 dedicated-PostgreSQL tests skipped,0 failures/errors.
- Source-only acceptance and TestClient HTTP pass for all six values; existing local vector count708 before/after unchanged. This is a local Task10 SQLite corpus, not the ECS PostgreSQL count.
- Frontend27 tests and TypeScript pass. Real HTTP responses pass frontend provenance/scope validation.
- Actual PDF row crops visually inspected in `work/task11-real/source-rows.png` (local evidence, excluded from package).
- Windows production build blocked by `spawn EPERM`; local Bash runtime blocked by Win32 signal-pipe error5. ECS wrapper runs `bash -n` and production build; do not treat these as locally passed.
- Independent code review found a period-metadata validation gap; fixed with real-PDF mutation tests and re-reviewed with no remaining P1/P2.
- ECS deployment and PostgreSQL/API regression remain pending until server output is received. Browser desktop/mobile/theme/keyboard/manual amount adjudication remain distinct acceptance steps.
