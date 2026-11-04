# FinSentinel API

Python 3.11+. From this directory:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
python -m pytest -q
```

Open `/docs` for OpenAPI. `DATABASE_URL` defaults to `sqlite:///./finsentinel.db`.
`DATA_MODE=synthetic_demo` seeds 24 teaching fixtures, 48 documents, 288 values,
and 40 golden fixture checks. Every financial value and risk event is invented;
they must never be presented as real disclosures or actual investment analysis.

Real data must use a separate database with `DATA_MODE=real_corpus` and
`CORPUS_PATH=../data/corpus.jsonl`. The corpus loader preserves source URLs,
page/paragraph locations and optional verified metrics. It does not fabricate
financial values when extraction fails.

This MVP uses deterministic planning/composition and lexical retrieval. It has
no external model calls, embedding benchmark or real financial accuracy claim.
Feedback is persisted and creates pending regression candidates, requiring
human approval before inclusion in scored cases. The `/evals/runs` endpoint
checks fixture calculations/citations/retrieval, and reports this scope.

## Day 5 API

From `backend/`:

```powershell
$env:PYTHONPATH = "."
python -m uvicorn app.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000/docs>. The v0.1 endpoints are `GET /api/v1/companies`, `GET /api/v1/companies/{company_id}/metrics`, and `GET /api/v1/evidence/{evidence_id}`. Missing companies, periods, metrics and evidence return 404 instead of synthetic fallback values.

## Day 6 growth API

Period-over-period growth is available at:

```text
GET /api/v1/companies/{company_id}/metrics/{metric}/growth?current_period=2026H1&previous_period=2025H1
```

The response contains both raw values, percentage growth, formula, source IDs,
and `data_mode`. Calculations use `Decimal`. Missing comparison periods, unit
mismatches and invalid baselines return explicit errors. Inventory is not
compared unless a verified prior period exists.
