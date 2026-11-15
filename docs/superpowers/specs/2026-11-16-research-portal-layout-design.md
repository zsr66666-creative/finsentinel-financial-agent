# FinSentinel research portal layout — reference-led design

Status: design prepared for user review, no application code changed. Task12 paused. Alibaba deployment is already authorized; no new deployment approval is needed.

## References and design direction
Reference1 (Kaggle screenshot): neutral white reading canvas, narrow white sidebar, black type and primary actions, cream selection, wide quiet search, editorial spacing, understated summary numbers, occasional pale yellow entry surfaces. Reference2 (CSDN screenshot): grouped left navigation, horizontal topic filters, central list and supporting right rail. Borrow their spatial hierarchy and color proportions; retain FinSentinel identity and finance business. Do not copy logos, social feeds, membership, ads or creator functions.

Recommended approach: reorganize current functions into a research portal with independent destinations. A styling-only refresh would preserve today's overloaded homepage; a social/content community would require unrelated backend features. Use the portal approach.

## Layout
Desktop sidebar240px (collapsible), topbar72px, flexible central content and optional right rail280px at wide widths. Maximum content width avoids excessively wide reading lines; no fixed-width canvas. Below1200px stack the right rail below main content; below768px use an accessible nav drawer and one content column. Navigation supports keyboard, Escape/focus return for drawer, visible focus and44px touch targets.

Home first screen: greeting using current local nickname, concise research description, real scope summary (indexed companies, report scopes/documents, chunks; derive actual counts), three functional entry tiles (company research, report library, evidence comparison). Below: industry filters and list of actual indexed company/report entries. Right rail: source/index coverage, links to supported research, and explanation of candidate vs source-validated vs human-reviewed data. No fake streaks, rankings, risk numbers, recent activity or invented reports. Loading, empty, error/retry and disconnected states remain explicit.

## Functional partitions
- Research home `/`: overview and real research entrypoints, not a long combined alert/detail workbench.
- Company library `/companies`: searchable actual indexed companies, industry filtering, actual scope metadata; click opens existing `/companies/[companyId]`.
- Report library `/reports`: source catalog grouped by company/report scope with physical-page coverage, original source locators available from existing evidence contracts/catalog; only expose a source link when a verified existing URL is actually available. A report entry opens its company/relevant search context, never a placeholder report detail.
- Original evidence `/evidence`: reuse actual scoped text retrieval component, company and period filters, preserve candidate-only boundary and advanced upload.
- Evidence comparison `/compare`: retain existing reviewed question workflow and result logic; company pages retain Task11 three-metric financial comparisons.
- Demo workbench `/workbench`: preserve current monitoring, workflow analysis and demo company functionality. Subsections for alerts, alert review, evaluation/version and data quality are independently addressable via validated subroutes or URL-backed views; sidebar groups them under a clearly labelled demo workbench. This is existing alert feedback, not new Task12 financial adjudication.
- Personal `/settings`: preserve nickname/avatar and theme preferences; keep current demo login/return behavior and mark it as demo. `/login` follows typography/palette but remains a focused login screen.

Shared sidebar/topbar must be consistent across pages. Rename obsolete consumer-electronics-only workspace wording to cross-industry financial research. Top search finds companies by name/code and navigates to real company pages; scoped evidence search stays in its dedicated form. Retain clear distinction if demo company search is also exposed. Filtering does not imply server-wide document full-text search.

## Palette and components
Light: white/near-white surfaces, neutral gray rules, near-black text, cream active selection; charcoal primary buttons. Pale yellow can highlight the three entrance tiles, with only restrained muted sage/blue complementary accents. Semantic teal/amber/red remain reserved for evidence/needs-review/error meaning. No large ambient multi-color gradients, stacked translucent cards, large background decoration or repeated heavy KPI tiles. Preserve readable CNY numbers, source text and hashes.
Dark: charcoal background and raised neutral surfaces, light type, warm dark selection, low-intensity yellow accents; retain all semantic statuses and system/light/dark persistence. Follow current system font stack and compact table numerals. Use a coherent inline SVG line-icon set, no unrelated emoji styles. Motion only for immediate interaction feedback; reduced-motion compatible.

## Existing behavior and scope boundaries
Do not change backend APIs, DB schema, index, financial contracts or report counts. Keep actual source acquisition outside public UI. Do not add community, subscription, genuine authentication, new financial review persistence or report export in this layout task. All existing working interactions retain reachable destinations, including analysis runs, alert feedback, evaluation and data-quality operations. Do not make unavailable Task12 actions look operational.

Existing login safe-return allowlist must be extended for any real new routes, with rejection tests for external/scheme-relative/malformed redirects. Old deep links and company pages remain usable. Saved nickname/avatar/theme are preserved. Derive catalog summaries from a shared fetch/state to avoid duplicated requests and inconsistent counts.

## Implementation units and verification
1. Shared shell/navigation/search/icons and neutral semantic tokens with dark/mobile variants.
2. Extract existing workbench into reachable destination(s), keeping business logic intact; home becomes actual research overview.
3. Catalog-backed company/report pages and dedicated evidence page; shared data loading, real filters, no fixtures on real pages.
4. Apply consistent shell to compare/company/settings and safe login returns, preserving financial review boundaries.
5. Test navigation/return paths/catalog grouping/filtering/empty and error behavior; all frontend tests, TypeScript and production build. Check actual desktop/mobile/dark/keyboard layout and all current business flows. Backend contracts unchanged, targeted API regressions only as needed.
6. Commit/push and prepare a hash-verified offline ECS source deployment package using the proven build/stage/static-asset-preservation/rollback method. Extend Nginx page+asset checks to every new route. Distinguish local tests, cloud build/API checks and browser acceptance. No Nginx edits or open backend ports.

## User-visible design summary
A light, quiet research portal: grouped white sidebar, a wide company search on top, a clear welcome/summary area, three research entrances, then a filterable report/company list with a compact source-coverage rail. Independent pages carry detailed research and tools. Existing functionality remains available and real data stays separate from demo monitoring.
