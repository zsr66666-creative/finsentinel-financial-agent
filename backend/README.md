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
