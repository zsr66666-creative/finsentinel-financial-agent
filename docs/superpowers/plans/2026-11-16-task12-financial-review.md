# Task12 implementation plan

Goal: persist source-bound human decisions and export exact financial research reports; preserve portal.
Architecture: additive standalone SQLAlchemy table + service/router/export; company card review UI; offline ECS stage/build/backup/switch.

- [x] Tests first: fingerprint changes on amount/proof/scope; source unavailable forbids decision; idempotency exact replay/conflict; stale version conflict; append history persistence; no carry-over across source changes; unauthorized/disabled write; export exact values/pending/rejected/escaped notes.
- [x] Implement backend dedicated financial_reviews service, additive migration, guarded router and JSON/Markdown export. Keep Task11 API stable.
- [x] Add typed frontend review response validation/tests; per-company report downloads and per-metric review forms, history, error/concurrency/retry states. Preserve portal and dark/mobile layout.
- [ ] Local backend/front tests and TS, review and fix; ECS acceptance script for actual six source-bound snapshots plus isolated persistence and HTTP export checks.
- [ ] Create frontend/backend offline installer, backup and rollback, verified package and GitHub push; provide one console command. Cloud/manual acceptance remain pending until logs.

## Verification

34 targeted backend tests (SQLite persistence/concurrency + actual local source contracts) and 33 frontend tests pass; TypeScript and CSS parsing pass. Independent review found and fixed missing Authorization CORS header and final multi-service success gate; added regression and individual checks. Embedded installer Python compiles. Windows production build attempted: spawn EPERM. ECS Bash syntax/build/PostgreSQL/concurrency/HTTP and manual browser acceptance remain pending, not claimed as passed. No production review records created locally.
