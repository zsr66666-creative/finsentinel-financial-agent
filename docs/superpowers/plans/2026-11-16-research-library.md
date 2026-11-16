# Personal Research Library Implementation Plan

**Goal:** Persistent private company/evidence favorites, notes and research history deployed to ECS.
**Architecture:** SQLAlchemy owner-scoped tables and authenticated routes; server derives immutable source snapshots, Next.js personal library and interaction hooks.
**Global constraints:** Follow approved research-library-design.md; no new dependencies, anonymous rejected, user id only from session, CSRF retained, backups never relaxed.

- [ ] Task1 backend: add personal_research.py repository/migration and personal_research_routes.py. Test anonymous/CSRF/owner isolation, server source derivation, duplicate favorites, note limits, pagination, history pruning/reopen URLs, restart persistence. Expose migration via scripts.manage_research_library migrate/check.
- [ ] Task2 frontend: reusable research-library client actions/parser, /my-research and portal nav; favorite controls company/evidence and successful history recording with safe prefilled reopening. Node tests for contract/links, tsc and Linux build.
- [ ] Task3 deployment: dedicated source-only package installer; trusted source permissions, app-owned test temp, pre-switch pg_dump, additive migration, production build static retention/TLS+401 smoke, rollback app config only. Preserve running ops timers. Update README/docs.
- [ ] Task4 final: independently review isolation/snapshot/input/persistence/delivery, run full backend/frontend/PG CI, push verified main, deterministic tar manifest+SHA; ECS user console execution then browser acceptance.
