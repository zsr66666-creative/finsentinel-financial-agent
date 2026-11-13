# Modern Financial SaaS UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a unified, responsive FinSentinel SaaS shell and apply it to the overview and evidence comparison pages.

**Architecture:** Keep existing page-level data and API behavior. Centralize visual tokens and shell styles in `frontend/src/app/globals.css`, then update the two page compositions to share navigation, heading, status, and evidence presentation patterns.

**Tech Stack:** Next.js 15, React 19, TypeScript, CSS modules through the existing global stylesheet, existing npm test/build scripts.

## Global Constraints

- Preserve all existing API paths, request payloads, fixture fallback, and review actions.
- Do not add a UI component dependency or change backend contracts.
- Use CSS variables for palette and spacing so the visual direction can be replaced later.
- Keep status meaning explicit in text and accessible labels.

---

### Task 1: Establish shared visual tokens and responsive shell styles

**Files:**
- Modify: `frontend/src/app/globals.css`

**Interfaces:**
- Produces token classes and shell styles consumed by both `page.tsx` and `compare/page.tsx`.

- [ ] Add tokens for page background, panel, text, muted text, border, accent, success, warning, danger, spacing, radius, and shadow.
- [ ] Normalize focus-visible, button, input, textarea, select, and link behavior.
- [ ] Add responsive rules that stack panels below 900px and convert sidebar navigation below 720px.
- [ ] Preserve existing class names while consolidating duplicated comparison styles.
- [ ] Run `npm run build` from `frontend` and confirm the stylesheet compiles.

### Task 2: Refine the overview shell without changing data behavior

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/app/globals.css`

**Interfaces:**
- Consumes existing `request`, `loadDashboard`, alert/company state, and navigation state.
- Produces the same actions and labels with improved visual hierarchy.

- [ ] Keep the existing sidebar navigation and add consistent active, hover, and keyboard states.
- [ ] Keep the topbar connection indicator and make demo/API state visible as text.
- [ ] Group the overview metrics, risk distribution, workflow, alert list, and detail panel using the shared panel tokens.
- [ ] Keep review, analysis, ingestion, and feedback handlers unchanged.
- [ ] Run `npm test` and `npm run build`.

### Task 3: Bring `/compare` into the shared product shell

**Files:**
- Modify: `frontend/src/app/compare/page.tsx`
- Modify: `frontend/src/app/globals.css`

**Interfaces:**
- Consumes existing compare endpoint and `Result` type.
- Produces the same supported and needs-review output, with source evidence and values preserved.

- [ ] Replace the standalone page header with a compact shell header and return navigation.
- [ ] Present the query form in a panel with example chips, clear label, loading state, and accessible error state.
- [ ] Present supported results as a verdict panel, period comparison cards, and evidence list.
- [ ] Present `needs_review` as a distinct warning state with reason text and no fabricated values.
- [ ] Verify the same-origin request path remains unchanged.

### Task 4: Verification and visual regression checks

**Files:**
- Test: `frontend/tests/*.test.mjs` (existing tests only unless a missing behavior is exposed)

- [ ] Run `npm test`.
- [ ] Run `npm run build`.
- [ ] Start the app locally and check `/` and `/compare` at desktop and narrow viewport widths.
- [ ] Confirm no horizontal overflow and that API/demo/error states remain readable.
- [ ] Record any limitation that requires manual browser review.
