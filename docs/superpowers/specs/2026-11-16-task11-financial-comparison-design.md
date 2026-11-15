# Task 11: source-bound financial comparisons

Approved scope: 002555 and 002230, 2024FY consolidated revenue, accounts receivable and operating cash flow. Preserve existing comparison and demo APIs.

## Design
Use a committed six-row source contract bound to exact official PDF SHA256, document identity, physical pages and whitespace-normalized exact excerpts. Read ingestion_artifacts and local PDF only; never derive authoritative numbers from nearest-neighbor hits. Verify company/year/type, full PDF hash, table title, unit, period headers, metric row and continuity across adjacent pages. Source validation is machine evidence validation, not human adjudication; review_status stays pending_human. No database migration or new metric persistence.

GET /api/v1/companies/{code}/financial-comparison?period=2024FY&statement_scope=consolidated returns three independently validated metrics. Unsupported company/period/scope or missing/substituted source returns needs_review without numeric fields. Unexpected infrastructure failure is 503. Use Decimal arithmetic; percentage=(current-previous)/abs(previous)*100, rounded half-up to 2dp; previous zero => null with reason. State raw comparison dates, including 2024-01-01 on 002230 balance sheet; do not relabel as 2023-12-31. 002555 opening balance remains labelled 期初余额 with explicit annual-balance semantics.

Company page adds a semantic-token macOS-style card, scope/period controls, loading/empty/error/retry states, exact CNY figures, neutral increase/decrease (not risk colors), accessible source details and official PDF links. No images, dependencies, sidebar/theme changes. Cancel and suppress stale requests on company/scope changes. Keep demo section clearly separated. No LLM or generic financial conclusions.

## Delivery and acceptance
TDD for arithmetic, unavailable evidence, wrong source/company/scope and real-PDF end-to-end. Frontend tests validate response provenance and scope. Production build runs on ECS. Offline installer reuses Task10 runtime, stages while old site serves, takes PG backup, switches backend and standalone atomically with rollback, preserves static assets; validates six metrics against pinned expectations via direct and Nginx HTTP, rechecks Task10 retrieval and original comparison. Do not reindex or change ingestion jobs. Browser acceptance remains separate. Deploy to Alibaba authorized by user.
