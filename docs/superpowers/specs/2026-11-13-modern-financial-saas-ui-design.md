# Modern Financial SaaS UI Design

## Goal
Create a unified FinSentinel product shell inspired by the information density and navigation patterns of shadcn dashboard starters while preserving existing financial evidence workflows.

## Scope
- Unified shell for the dashboard and `/compare`.
- Reusable design tokens for colors, spacing, borders, status states, and responsive breakpoints.
- Refined overview dashboard, alert/evidence panels, and comparison workflow.
- Preserve existing API calls, fixture fallback, review actions, and evidence semantics.

## Visual direction
Use a restrained financial SaaS palette through CSS variables so a later reference style can replace the palette without rewriting components. Use tinted neutrals, hairline borders, calm shadows, compact typography, and explicit states for connected/demo/error/supported/review.

## Interaction
The shell provides persistent navigation, workspace context, API/data status, page heading, and responsive navigation. The compare flow presents question input, supported/review state, period values, difference, statement scope, and source evidence in that order.

## Accessibility and responsive behavior
All controls retain labels and keyboard focus. Status is exposed with text, not color alone. At narrow widths, the sidebar becomes a compact top navigation and panels stack to one column.

## Acceptance
- Existing API endpoints and review behavior remain unchanged.
- `npm run build` passes.
- Existing frontend tests pass.
- `/` and `/compare` render with the same shell and no horizontal overflow at desktop and narrow widths.
