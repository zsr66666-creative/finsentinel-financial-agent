# Task12 financial adjudication and export design

User approved the Task12 proposal on 2026-11-16 and instructed execution and default ECS delivery. Scope: six Task11 source-verified metrics, persisted confirm/reject/needs-evidence history, downloadable research reports. Preserve the portal and old demo feedback.

## Contract

Each decision binds a server-generated immutable snapshot of one source-verified metric (company, report, statement scope, periods, exact decimals, PDF hash, proof hashes/pages). Canonical JSON SHA-256 is the snapshot fingerprint. Client submits fingerprint, expected latest review id, idempotency key, decision, reason, self-declared nickname; never submits authoritative amounts. Optimistic concurrency rejects stale decisions. Append-only rows and idempotent requests survive restarts. A changed or unavailable source never inherits confirmation. Even confirmation is self-declared operator review, not certified identity or investment advice.

Separate FINANCIAL_REVIEW_TOKEN protects writes, disabled if absent. Token entered per submission, never persisted in profile/session storage, never exported. Read history and JSON/Markdown export public, like existing public research. Fixed supported scope only, bounded inputs/history, rate-limited writes. Latest id required for edits; no deletes or source-number mutation. Review status separate from Task11 source_validation/pending_human fields to avoid silently changing existing API contracts.

## UI and exports

Company financial cards expose an independent review panel with history and confirm/reject/needs-evidence form. User must explicitly choose and explain action; no default confirmation. Whole-company report downloads JSON or Markdown generated server-side from freshly verified sources and matched review fingerprints. Report contains exact original periods, amounts, proofs, physical pages, hashes, source URLs, pending/rejected statuses, limitations and export timestamp. A changed source resets the current review overlay; historical decisions remain visible. Markdown escapes user-controlled text and cannot inject executable markup. No PDF, new auth, multiuser identity claims or financial-number correction UI in this stage.

## Persistence and deployment

Additive migration 005 creates dedicated financial review table with unique idempotency key; transactions serialize latest-id comparison and insert (PostgreSQL advisory lock; SQLite write transaction for tests). Existing artifact/index data unchanged. Service module, route module and export renderer isolated. Offline package stages complete backend+current portal frontend, tests/builds before switch, takes database backup, applies additive migration, adds backend drop-in and review env, retains old service/frontend rollback. Migration retained on rollback; no destructive down migration during normal deployment. Server acceptance must verify persistence/concurrency in an isolated schema/test database and six real source contracts without making production human review decisions.
