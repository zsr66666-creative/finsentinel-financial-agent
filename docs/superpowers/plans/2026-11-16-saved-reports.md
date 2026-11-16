# Saved Research Reports Implementation Plan

> **For agentic workers:** Use subagent-driven-development task-by-task with review checkpoints.

**Goal:** Save server-derived private financial research snapshots, reopen and export them.
**Architecture:** Explicit additive SQLAlchemy migration; authenticated owner routes; immutable existing research_export snapshots; portal list and detail.
**Tech Stack:** Existing FastAPI, SQLAlchemy, PostgreSQL/SQLite, Next.js and CSS. No dependencies.

## Global Constraints
Owner from session only; CSRF writes; snapshots <=2MiB; 200 reports per owner; supported scope002555/0022302024FYconsolidated only; no fabricated numbers; no runtime migration.

### Task1 Backend
- [ ] Add tests/test_saved_reports.py first: migrate twice; owner1 save using server-derived export; mutate current source then reopen/export same snapshot; owner2 detail/delete/export404; no session401; injectedsnapshot422; limit/pagination; deletion. Observe RED.
- [ ] Implement app/saved_reports.py schema, migration/check and owner-scoped operations; app/saved_report_routes.py request models and exports; wire main; scripts/manage_saved_reports.py explicit CLI. Reuse app.research_export, company_comparisons and accounts transaction patterns. Run focused tests and startup regression.
- [ ] Review backend spec and quality before frontend integration.

### Task2 Frontend
- [ ] Add saved-reports.mjs parser and Node tests for snapshot identity, missing/zero, safe URLs, malformed data. Observe RED then implement.
- [ ] Add save form to verified-financials, reports list to personal-research and research-reports/[id] details. Use authFetch/researchWrite, cancellation and owner guards; render snapshots with React text and ReaderLink, download server export via authenticated fetch.
- [ ] Run Node suite, tsc and production build in CI; review UI/data boundaries.

### Task3 Delivery
- [ ] Adapt report-reader package/installer/smoke; backup+isolatedrestore before migrate/check; focused tests and trusted TLS read-only smoke; preserve old drop-in rollback and assets.
- [ ] Add PostgreSQL acceptance, CI bash check, docs and README. Verify full backend, frontend, schema persistence and archive manifest/LF.
- [ ] Commit/push branch; review final branch; wait CI; push main and verify remote revision; package committed sources and deliver console command. Cloud/browser remains pending until user logs.
