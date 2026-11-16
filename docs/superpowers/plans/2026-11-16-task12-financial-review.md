# Task12 implementation plan

Goal: persist source-bound human decisions and export exact financial research reports; preserve portal.
Architecture: additive standalone SQLAlchemy table + service/router/export; company card review UI; offline ECS stage/build/backup/switch.

- [ ] Tests first: fingerprint changes on amount/proof/scope; source unavailable forbids decision; idempotency exact replay/conflict; stale version conflict; append history persistence; no carry-over across source changes; unauthorized/disabled write; export exact values/pending/rejected/escaped notes.
- [ ] Implement backend dedicated financial_reviews service, additive migration, guarded router and JSON/Markdown export. Keep Task11 API stable.
- [ ] Add typed frontend review response validation/tests; per-company report downloads and per-metric review forms, history, error/concurrency/retry states. Preserve portal and dark/mobile layout.
- [ ] Local backend/front tests and TS, review and fix; ECS acceptance script for actual six source-bound snapshots plus isolated persistence and HTTP export checks.
- [ ] Create frontend/backend offline installer, backup and rollback, verified package and GitHub push; provide one console command. Cloud/manual acceptance remain pending until logs.
