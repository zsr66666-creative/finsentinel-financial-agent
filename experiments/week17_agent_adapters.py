import json
import subprocess
import time
from pathlib import Path


def run_condition(condition: str, script: str, output: str) -> dict:
    started = time.perf_counter()
    subprocess.run(["python", script], check=True)
    payload = json.loads(Path(output).read_text(encoding="utf-8"))
    payload["condition_alias"] = condition
    payload["runner_duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return payload


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    single = run_condition("single_agent", str(root / "experiments/week14/run_single_agent.py"), str(root / "data/evals/retrieval-run-week14-single-agent.json"))
    dual = run_condition("dual_agent", str(root / "experiments/week14/run_dual_agent.py"), str(root / "data/evals/retrieval-run-week14-dual-agent.json"))
    result = {"status": "adapter_only", "provider": "fake", "model": "deterministic-demo-v1", "conditions": {"single_agent": single, "dual_agent": dual}, "limitations": ["These are deterministic adapters, not real LLM measurements.", "Real provider quality, latency and cost remain unmeasured."]}
    Path(root / "data/evals/week17-agent-adapters.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"single_hit_count": single["hit_count"], "dual_hit_count": dual["hit_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
