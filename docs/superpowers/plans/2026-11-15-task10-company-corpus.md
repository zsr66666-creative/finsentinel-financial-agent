# Task 10 Company Corpus Implementation Plan

> **For agentic workers:** Use executing-plans inline. No implementation delegation is needed.

**Goal:** Add two user-approved A-share annual reports with real source-backed company navigation and deployable ECS acceptance.

**Architecture:** Fixed official source manifest -> existing persistent queue/worker -> Task 9 document indexing -> actual scope catalog/company profiles -> real-report directory and scoped company retrieval.

**Tech Stack:** Existing Python/SQLAlchemy/PostgreSQL, requests/PyMuPDF, pinned BGE ONNX, Next.js/React.

## Global constraints

Preserve previous indexes/compare. No fake metrics or new model. Only selected physical pages. Queue and source hashes gate publication. Same-origin Nginx, no new public ports. All features ship with Alibaba console deployment.

### 1. Source manifest and real company identity

Files: `data/manifests/task10-official-reports.json`, `backend/app/research_companies.py`, `backend/app/corpus_catalog.py`, `backend/app/main.py`, `backend/tests/test_task10_profiles.py`.

- [x] Write/run failing tests: a registry-only company returns 404 until indexed; indexed company profile has real-PDF mode and no synthesized metrics; existing profiles remain unchanged.
- [x] Add verified company metadata and catalog fields. For previously unknown company IDs only, provide an index-backed read-only company profile.

### 2. Real report navigation

Files: `frontend/src/components/real-report-library.tsx`, `frontend/src/components/evidence-search.tsx`, `frontend/src/components/company-research.tsx`, `frontend/src/app/page.tsx`, scope helper/tests.

- [x] Test grouping/index selection before UI edits.
- [x] Add real-report cards driven exclusively by actual scopes; preserve explicit synthetic monitor labeling.
- [x] New company pages render scoped original-text search and omit demo indicators/alerts. Scope prop filters catalog and invalidates late responses on company changes.
- [x] Run frontend tests and TypeScript; production build remains an ECS acceptance step if this host blocks workers.

### 3. Acquisition and indexing batch

Files: `scripts/task10_acquire.py`, `scripts/task10_acceptance.py`, shared installer, Task 10 wrapper/packager.

- [x] Run real PDFs through current parser and verify all indexed source text, page offsets, actual coverage and document encoding locally.
- [x] Enqueue two exact requests idempotently, wait with a bounded deadline, verify expected PDF hashes before indexes. Reuse existing Task 9 index CLI and report-level repeat checks.
- [x] Preserve Task 9 installer default; parameterize task/reports/acceptance without duplicating rollback. Keep committed additive data on rollback and disclose this behavior.
- [x] Verify original Task 9 acceptance plus new companies, correct scopes/source SHA/page text, no fabricated metrics, and all page assets.

### 4. Delivery

- [x] Run targeted regression tests, source/embedded-Python syntax and real ONNX checks; independently review correctness before integration.
- [ ] Commit/push and verify fresh remote main. Generate/check a source-only LF archive and full server command.
- [ ] Cloud install/build/PostgreSQL and browser interaction stay pending until console execution produces evidence.

## Verification boundary

55 backend passed,2 skipped (dedicated PostgreSQL URL unavailable);23 frontend passed;TypeScript passed. Real local PDFs produced708chunks with repeat0 and6company-isolated smoke queries using actual ONNX with SQLite/NumPycosine. Query/encoder runtime unchanged. Independent read-only review found no blockers. Local production build remains blocked by Windows spawn EPERM; cloud Bash/build/PostgreSQL and browser acceptance remain pending.
