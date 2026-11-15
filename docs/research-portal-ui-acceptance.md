# Research portal UI acceptance

This is a frontend-only redesign before Task12. It preserves the existing backend, database, ONNX encoder, corpus and public Nginx configuration.

New destinations: `/` research portal; `/companies` actual indexed companies; `/reports` actual indexed report/coverage list; `/evidence` original-text retrieval. Existing company details, `/compare`, login/settings and dark mode remain. Monitoring, analysis, feedback, evaluation/version and data quality moved to `/workbench` and its validated subsections. They remain explicitly demo monitoring, separate from real catalog data.

## Local evidence

- 31 frontend Node tests pass, including new catalog count/filter/scope/navigation tests.
- TypeScript `tsc --noEmit` passes.
- Portal CSS parses with PostCSS; installer embedded Python compiles.
- Production build was attempted on Windows but failed at child process creation (`spawn EPERM`); this is not a passing build. Installer runs `npm test` and `npm run build` on ECS before stopping the live frontend.
- Browser visual/business acceptance and cloud deployment remain pending until verified.

## ECS delivery

Upload the hash-verified source-only archive to `/root/finsentinel-research-portal.tar.gz`. Extract to a new root-only directory, run `bash -n deploy/ecs/install-research-portal-offline.sh`, then run it as root. The installer validates a per-file manifest, stages/builds while the old site serves, preserves old hashed assets, and rolls back if switching or page/resource checks fail. No GitHub access is required by the installer; `npm ci` still needs the package registry or an already populated npm cache.

The deployment source revision is the `SOURCE_REVISION` file inside the archive. Existing `/opt/finsentinel` Git checkout is not updated by this standalone frontend deployment. A retained release and previous build path are printed on completion.

Checks cover application shells and referenced CSS/JS through Nginx for all new and existing routes. These HTTP checks do not prove authenticated browser interaction or real search correctness.

## Browser acceptance after deployment

1. Demo-login, then check homepage counts against `/api/v1/evidence/scopes`; empty/error states never substitute fixtures.
2. Filter company list by industry and code/name. Use top search from another page and while already on `/companies`; URL and displayed results must agree. Open all three indexed company pages.
3. Open report coverage details, follow report to the exact company/period in `/evidence`. Invalid or incomplete URL contexts show an explicit warning without switching scope.
4. Submit text retrieval, change scope during a request, and check only the latest matching scope appears. Candidate-only warnings remain.
5. Check existing reviewed comparison and company financial comparisons. Unsupported cases show needs_review without invented amounts.
6. Open each workbench subsection and verify existing analysis, alert feedback, evaluation and data-quality functions still work.
7. Verify nickname/avatar, logout/login return paths and light/dark/system persistence.
8. At desktop and 390px width: no page overflow, readable numbers and source hashes, mobile drawer group labels visible, Escape closes drawer, keyboard focus visible. Refresh every route with no CSS/JS 404.
