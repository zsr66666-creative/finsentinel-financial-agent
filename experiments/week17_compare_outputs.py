import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run(root: Path, script: str, output: str) -> dict:
    subprocess.run([sys.executable, str(root / script)], cwd=root, check=True)
    return json.loads((root / output).read_text(encoding="utf-8"))


def normalize(name: str, payload: dict) -> dict:
    total = payload.get("dataset_scorable_questions", payload.get("dataset_total_questions", 0))
    evaluated = payload.get("evaluated_case_count", 0)
    metrics = payload.get("metrics", {})
    hits = payload.get("hit_count")
    errors = sum(1 for row in payload.get("results", []) if row.get("error") or row.get("status_code", 200) >= 400)
    values = [row.get("duration_ms", row.get("analysis_duration_ms", 0)) for row in payload.get("results", [])]
    values = sorted(v for v in values if isinstance(v, (int, float)))
    p50 = metrics.get("p50_latency_ms", values[len(values) // 2] if values else None)
    p95 = metrics.get("p95_latency_ms", values[max(0, int(len(values) * .95) - 1)] if values else None)
    return {"condition": name, "hits": hits, "total": total, "evaluated": evaluated, "failure_count": errors, "failure_rate": errors / evaluated if evaluated else None, "p50_latency_ms": p50, "p95_latency_ms": p95, "cost_usd": metrics.get("cost_usd", 0.0), "provider": payload.get("provider", payload.get("model_version")), "model_version": payload.get("model_version"), "prompt_version": payload.get("prompt_version"), "corpus_version": payload.get("corpus_version"), "dataset_manifest": payload.get("dataset_manifest")}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    baseline = run(root, "experiments/week14/run_deterministic_baseline.py", "data/evals/retrieval-run-week14-deterministic-baseline.json")
    single = run(root, "experiments/week14/run_single_agent.py", "data/evals/retrieval-run-week14-single-agent.json")
    dual = run(root, "experiments/week14/run_dual_agent.py", "data/evals/retrieval-run-week14-dual-agent.json")
    output = {"status": "adapter_only", "generated_at": datetime.now(timezone.utc).isoformat(), "code_version": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(), "conditions": [normalize("deterministic_baseline", baseline), normalize("single_agent", single), normalize("dual_agent", dual)], "limitations": ["Deterministic adapters only; no real LLM quality measurement.", "Synthetic fixture remains separate from real PDF golden set."]}
    (root / "data/evals/week17-comparison-summary.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
