# Report Reader Implementation Plan

**Goal:** Authenticated source-verified PDF reader and physical page links, shipped to ECS.
**Architecture:** Server resolves evidence locators and registered PDF SHA; native PDF rendering via same-origin range endpoint; frontend safe links and independent reader.
**Constraints:** approved report-reader-design.md; no external PDF fetch, no paths from client, no new dependency/schema, retain auth/TLS/operations/private research.

- [ ] Backend: reader resolver/routes+range support tests with actual PDFs; wire main, source-bound SHA+page no symlinks/no raw exceptions. GET/HEAD 401 anonymous and AUTHdisabled. Run focused tests.
- [ ] Frontend: lib reader locator/parser tests; reader page+links in existing surfaces, native PDF fallback and physical page controls; tsc+Node suite and CI build.
- [ ] Delivery: source-only package, pinned verified staging/build/backup+restore/switch/rollback, TLS smoke and docs; no schema migration needed. Tests for endpoint/privacy/delivery invariants.
- [ ] Final: independent source review, full tests+CI, verified main push, package SHA256 and single console command; user cloud/browser acceptance.
