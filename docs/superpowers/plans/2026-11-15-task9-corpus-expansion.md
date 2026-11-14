# Task 9 Corpus Expansion Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Publish the acquired 2024FY selected pages as traceable evidence, expose indexed scopes, and deliver an offline ECS rollout.

**Architecture:** A controlled indexing CLI verifies the artifact and original PDF before document encoding. All chunks and their coverage metadata publish in one transaction. A read-only catalog derives scopes from actual fixed-model vectors; the UI binds requests to a selected scope.

**Tech Stack:** Existing Python/SQLAlchemy/PostgreSQL, pinned BGE ONNX/tokenizers, Next.js/React/CSS.

## Global Constraints

- Preserve existing 14 reviewed/development vectors and monetary comparison.
- No new model weights, public ports, UI framework or runtime dependency.
- Documents have no query prefix; finite normalized 512-dimensional vectors only.
- Coverage is selected pages, not full-report coverage or adjudicated financial evidence.
- Every deployment shell uses LF; package integrity includes the installer.

### Task 1: Verified document indexing

Files: `backend/app/corpus_index.py`, `backend/app/query_encoder_service.py`, `scripts/task9_index.py`, `scripts/task9_encode_documents.py`, `backend/tests/test_corpus_index.py`, `backend/tests/test_query_encoder.py`.

Interface: `prepare_chunks(artifact, parsed, pdf_path) -> list[dict]`; `publish_chunks(engine, chunks, vectors) -> dict`; `Encoder.encode_document(text) -> dict`.

- [x] Write failing tests for changed PDF hashes, page/offset integrity, prefix separation, long-block splitting, idempotency, conflicting identity and transaction rollback.
- [x] Run `python -m pytest backend/tests/test_corpus_index.py backend/tests/test_query_encoder.py -q -p no:cacheprovider` with `PYTHONPATH=backend` and verify failures identify missing behavior.
- [x] Implement validated chunks and dialect-aware transactional inserts. Test with SQLite JSON storage and PostgreSQL casts at deployment.
- [x] Add administrator CLI: artifact root containment, temporary UTF-8 exchange, one encoder subprocess, strict output validation, metadata-only report.

### Task 2: Actual indexed scope catalog

Files: `backend/app/corpus_catalog.py`, `backend/app/main.py`, `backend/tests/test_corpus_catalog.py`.

Interface: `list_scopes(engine) -> dict` exposed as `GET /api/v1/evidence/scopes`.

- [x] Write failing API/catalog tests for model isolation, physical page coverage, empty DB and sanitized failure.
- [x] Group only actual nonempty indexed text under the pinned model, company/period/document, expose coverage and source status without local server paths.
- [x] Keep existing legacy scope visible and explicitly mark its coverage as indexed fragments. New text-search results use a neutral real-PDF candidate label.

### Task 3: Scope-bound retrieval interaction

Files: `frontend/src/components/evidence-search.tsx`, `frontend/src/lib/evidence-scopes.mjs`, `frontend/tests/evidence-scopes.test.mjs`, `frontend/src/app/globals.css`.

- [x] Test catalog parsing, company/period selection and response generation guards before implementation.
- [x] Fetch catalog with timeout/retry; show real company/period selectors, indexed pages and counts. Never fabricate options when catalog is unavailable.
- [x] Abort/invalidate old results on scope/question changes, file import and unmount; display submitted scope next to results and source URL/hash in evidence details.
- [ ] Run frontend unit tests, TypeScript and production build; document any local OS restrictions separately.

### Task 4: ECS deployment and acceptance

Files: `deploy/ecs/install-task9-offline.sh`, `scripts/task9_acceptance.py`, `scripts/package_task9.py`, `docs/task9-corpus-expansion.md`.

- [ ] Validate package checksums, current services, nginx and capacity before mutation; reuse installed encoder model/runtime and preserve old service drop-ins and frontend.
- [ ] Back up database before indexing; stop encoder only during bounded document encoding and restore it on all exits. Re-run indexing and require unchanged counts.
- [ ] Publish backend/frontend release with rollback; copy static assets for standalone and retain previous hashed assets.
- [ ] Verify real 2024FY source text/page/hash, old 2026H1/compare, Nginx catalog and text API, five pages/assets, service memory/restarts. No claims about independent benchmark accuracy.
- [ ] Package LF scripts from verified git blobs, push code and verify remote revision. Supply one complete console deployment command and explicit local/remote/manual status.

## Current verification status

- Local backend: 40 focused tests pass, including source mismatch, changed publication-set rejection and rollback.
- Local frontend: 22 tests and TypeScript pass. Actual ONNX/original-model document parity passes for three samples (maximum component error <2.1e-7).
- Local real PDF: 276 pages, 11 selected pages, 328 chunks, first insert328/repeat0, offline encoder peak220.8MiB.
- Production build and Bash execution are pending ECS validation: this Windows harness returns spawn EPERM and Git Bash signal-pipe Win32 error5. Python modules/embedded deployment blocks compile; actual package Shell bytes are separately checked for LF.
- ECS installation, PostgreSQL runtime acceptance and browser interaction remain pending until the supplied package is run on the server.
