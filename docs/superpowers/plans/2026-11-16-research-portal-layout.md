# Research portal layout implementation plan

> Execute inline using executing-plans; approved design in ../specs/2026-11-16-research-portal-layout-design.md.

**Goal:** reference-led light research portal with independent research destinations and intact existing tools.
**Architecture:** one catalog provider, shared responsive shell, route-backed legacy workbench, reusable company/report lists. Backend unchanged.
**Tech:** existing Next15/React19/CSS/Node tests, no new dependencies.

## Global constraints
User approved white/ink/cream with restrained pale yellow; dark parity. Real metrics/evidence stay distinct from demo monitoring. Preserve Task11 API and all existing actions. Alibaba deployment is authorized. Do not implement Task12.

- [x] Write portal helper tests first: real catalog counts/deduplication, combined industry/query filtering, exact company search, valid evidence deep-link context, safe new return paths and legacy section allowlist; run failure before implementation.
- [x] Implement portal helpers/types, shared catalog provider with cancellation/retry, outline SVG icons and shell with real company search, grouped nav, accessible mobile drawer and current route state.
- [x] Extract original dashboard intact to legacy-workbench; expose /workbench and valid /workbench/[section] routes. Preserve all business actions. Use shared shell in compare,company,settings and maintain safe demo login returns.
- [x] Implement actual catalog home, /companies and /reports pages with summary/filter/list/right rail and no fixture fallback; /evidence reuses scoped search with URL context and shared catalog.
- [ ] Add final neutral portal CSS after existing styles; preserve dense financial/data views and dark semantics. Record design. Test all frontend and TypeScript; run build, source/API regression as appropriate; inspect runtime at desktop/mobile/dark and business flows where environment permits.
- [ ] Independent review, fix findings, commit/push and verify remote. Create frontend-only offline ECS package with integrity hashes, old-build preservation, rollback and all new route/asset checks. Existing backend services and Nginx unchanged. User executes console command; remote acceptance pending until logs.

## Verification status

Implementation complete. 31 tests and TypeScript passed; CSS and embedded installer Python syntax passed. Windows production build blocked by spawn EPERM; ECS build and browser visual/business acceptance pending. Independent review complete; fixed same-route company query synchronization and inherited mobile drawer visibility. Installer static review has no remaining blocker.
