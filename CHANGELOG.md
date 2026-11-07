# Changelog

## v0.1.0-rc1

- Evidence-driven FastAPI and Next.js research workbench.
- Financial formulas and risk rules use deterministic, typed tools.
- Alerts expose evidence, metrics, execution trace and human review actions.
- BM25, query expansion and local embedding evaluation records are kept under `data/evals/`.
- Synthetic demo mode is explicitly separated from real-corpus mode.
- CI covers backend imports/tests and frontend tests/build.

### Known limitations

- Real LLM provider comparison is not configured; Week 14 uses deterministic adapters.
- Container end-to-end verification depends on Podman/Docker image registry access.
- Browser visual acceptance and external user trials require manual execution.
- No investment advice, trading signal or performance promise is provided.
