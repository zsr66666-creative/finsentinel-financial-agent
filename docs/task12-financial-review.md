# Task12 — source-bound financial review and research exports

## Scope and identity

Six fixed financial comparisons for 三七互娱 (002555) and 科大讯飞 (002230), 2024FY consolidated: revenue, receivables, operating cash flow. Task11 source-verification API remains unchanged. Source verification is separate from human review; the original `review_status=pending_human` describes that machine contract only. The new review overlay and report show current operator decisions.

Review actions: confirmed, rejected, needs_evidence. These decisions do not edit source numbers. All notes and self-declared reviewer names are public, just like evidence history. Demo login/nickname is not real identity authentication. Never claim reviewer identity has been certified.

Writes require a separate `FINANCIAL_REVIEW_TOKEN` of >=32 chars, no default/fallback token. The ECS installer generates 64 hex characters at `/etc/finsentinel/financial-review.env`, root:finsentinel 0640; systemd reads this file. Credential is never printed by installer, exported, or saved in profile/browser storage. Do not send it in chat. Read it only in the server console when needed. Existing public HTTP does not encrypt bearer credentials in transit: use an HTTPS origin or a trusted loopback/tunnel connection for operator submissions; public research/history/report downloads do not need a credential. Real authenticated multiuser accounts and TLS provisioning are outside this stage.

## API

- GET `/api/v1/companies/{code}/financial-reviews?period=2024FY&statement_scope=consolidated`: freshly verify PDFs, return each metric's current snapshot/fingerprint, latest matching decision and bounded history (up to 30, including effective matching latest even if older).
- POST same URL, `Authorization: Bearer ...`: strict fields `metric`, `fingerprint`, `expected_review_id` (null for no current decision), `idempotency_key` (16–100 ASCII key chars), `decision`, `reason` (3–1000 trimmed characters), `reviewer` (1–40). No client authoritative financial values. 401 unauthorized, 503 writes disabled/store unavailable, 409 stale source/version or conflicting idempotency, 422 unsupported scope/source/input, 429 >10 writes/min/process.
- GET `/api/v1/companies/{code}/research-report?format=json|markdown`: current server source verification and matched review status, original periods/columns/decimal strings, PDF hash, physical pages and proof text/hashes, export timestamp and limitations. Response is attachment/no-store/nosniff. Rejected values are explicitly not endorsed; source unavailable omits numbers.

Snapshot SHA-256 covers canonical JSON of the complete server-verified metric. Decision has immutable snapshot, predecessor id and UTC timestamp. Same key+same request replay returns original result, different request conflicts. PostgreSQL transaction advisory lock serializes latest-id check and insert; SQLite `BEGIN IMMEDIATE` supports meaningful local concurrency tests. New source has pending status and cannot inherit previous confirmation. A currently unavailable PDF cannot be reviewed, regardless of history. Concurrent operator notes preserve only one winning version and reject stale writes.

Migration `005_financial_reviews` is additive and explicitly invoked by deployment; not silently run on GET or startup. It creates dedicated review storage + index, independent of demo feedback. Application exposes no update/delete review API. This is application append-only history, not a tamper-proof external audit ledger.

## UI

Company → 真实财务核对 → 人工复核与研究报告. Choose decision explicitly, enter basis and per-submission operator credential. History refresh, loading/errors, stale-source refresh and request-timeout handling are provided. On uncertain POST, same unchanged submission retains its idempotency key until success/unmount; refreshing history can confirm whether it committed. Downloaded report is generated from current server sources, so may be newer than the page's cached snapshot. Existing portal/dark/mobile/pseudologin remain.

## Delivery and acceptance

`python -m scripts.package_task12 --output <archive>` packages committed source only. Installer validates manifest, runs frontend tests/build and targeted backend tests before live switch, preserves prior hashed assets, takes pg_dump, applies migration, runs six-real-source plus temporary PostgreSQL schema persistence/concurrency checks, adds only a new backend systemd drop-in, then switches frontend. Failures after switch restore previous backend drop-in/frontend. Additive table/records remain on rollback; no destructive database restore overwrites user decisions. No encoder restart, reindex, model download, new PDF or Nginx config edits. Registry access/npm cache remains needed for npm ci.

Acceptance successful writes occur only in a temporary PostgreSQL schema and are removed, never classified as human business review. Production API checks confirm anonymous writes fail, current histories/exports align with all six source contracts, unsupported scope is refused, legacy comparison still works, and all portal routes/assets respond. Cloud build, PostgreSQL and HTTP checks require actual server logs; browser form/download/theme/keyboard/mobile checks remain separate.

Local: targeted backend tests (including CORS browser preflight), frontend Node tests and TypeScript. Windows next build and bash -n may be blocked by host subprocess permissions; do not report those as passing. Actual ECS build/shell syntax run before switch.
