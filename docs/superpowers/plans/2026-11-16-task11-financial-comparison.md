# Task 11 implementation plan

> For agentic workers: execute inline using executing-plans with verification-before-completion.

**Goal:** source-bound three-metric comparisons for two official 2024FY reports.
**Architecture:** immutable PDF contracts + read-only source verification + Decimal calculation + isolated company component.
**Tech stack:** FastAPI, SQLAlchemy, PyMuPDF, Next.js, React, existing CSS tokens.

## Global constraints
No new dependency, database schema, LLM, vector publication, demo values or human-reviewed claim. Preserve Task10 and original reviewed comparison. Alibaba deployment is required, cloud acceptance pending until measured.

- [ ] Source contracts: inspect report tables, title/unit/year headers, raw comparison dates; save six exact excerpt contracts in backend/app/data/task11-financial-contracts.json. Verify pinned PDF bytes, render source crops for visual QA.
- [ ] Backend: add backend/tests/test_task11_financials.py first; run pytest to see missing-module failure. Implement backend/app/verified_financials.py with calculate_change and company_comparisons(engine,code,period,scope,artifact_root); add GET financial-comparison endpoint. Tests include zero/negative base, mismatched DB metadata, missing files, changed text, unknown scope, response no numeric values on refusal.
- [ ] UI: write frontend/tests/verified-financials.test.mjs first, run node tests and see missing-module failure. Implement parseFinancialComparison(body,code,period,scope), formatFinancialNumber(value), declarations, and VerifiedFinancials company component; integrate it above evidence search, avoid duplicate demo indicator labels.
- [ ] Deployment: standalone deploy/ecs/install-task11-offline.sh builds old-site-safe, validates exact package hashes, backs up DB and existing backend drop-in, preflights source with staged code, uses trap rollback for service changes, runs scripts.task11_acceptance directly and via Nginx plus Task10 regression, no indexing. Package scripts/package_task11.py from committed sources.
- [ ] Verify: targeted backend regressions, all frontend tests, tsc, source visual QA, package paths/hashes/LF/embedded Python syntax; production build on ECS. Request independent read-only review, resolve substantive issues, commit and push with fresh remote ref verification. Deliver archive hash and one complete console command. Never claim cloud success before logs.
