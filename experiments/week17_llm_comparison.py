"""Run the v0.2 Week 2 comparison protocol.

The default mode is a dry run so CI never calls an external model. Real runs
require MODEL_PROVIDER=openai-compatible and an API key supplied by the shell.
"""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.model_config import ModelSettings


def git_version() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/evals/week17-llm-comparison.json")
    parser.add_argument("--execute", action="store_true", help="allow configured real provider; no API key is read from files")
    args = parser.parse_args()
    settings = ModelSettings.from_env()
    if args.execute and settings.provider == "fake":
        raise SystemExit("--execute requires MODEL_PROVIDER=openai-compatible")
    result = {
        "status": "ready" if not args.execute else "not_run",
        "mode": "real_provider" if args.execute else "dry_run",
        "provider": settings.provider,
        "model": settings.model,
        "dataset": "data/evals/golden_questions.jsonl",
        "dataset_split": "development only until protocol is frozen",
        "corpus_version": "week10-multi-company-v3",
        "conditions": ["deterministic_baseline", "single_agent", "dual_agent"],
        "metrics": {"hits": None, "total": None, "p50_latency_ms": None, "p95_latency_ms": None, "failure_rate": None, "cost_usd": None},
        "code_version": git_version(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limitations": ["dry run has no quality or latency measurements", "synthetic fixtures and real corpus remain separate"],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
