"""Run the v0.2 Week 2 comparison protocol.

The default mode is a dry run so CI never calls an external model. Real runs
require MODEL_PROVIDER=openai-compatible and an API key supplied by the shell.
"""
import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.model_config import ModelSettings
from app.providers.openai_compatible import ModelProviderError, OpenAICompatibleProvider


def git_version() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_cases(path: str, max_cases: int) -> list[dict]:
    cases = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = [case for case in cases if case.get("split") == "development" and case.get("type") != "correct_refusal"]
    context_path = Path("data/evals/week17-evidence-context.json")
    context_map = json.loads(context_path.read_text(encoding="utf-8")) if context_path.exists() else {}
    for case in cases:
        case["evidence_context"] = [{"id": evidence_id, **context_map[evidence_id]} for evidence_id in case.get("gold_evidence_ids", []) if evidence_id in context_map]
    return cases[:max_cases]


def parse_model_output(text: str) -> dict:
    candidate = text.strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", candidate, flags=re.S)
        if not match:
            return {"answer": candidate, "evidence_ids": [], "valid_json": False}
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"answer": candidate, "evidence_ids": [], "valid_json": False}
    if not isinstance(value, dict):
        return {"answer": candidate, "evidence_ids": [], "valid_json": False}
    evidence_ids = value.get("evidence_ids", [])
    if not isinstance(evidence_ids, list) or not all(isinstance(item, str) for item in evidence_ids):
        evidence_ids = []
    return {"answer": value.get("answer"), "evidence_ids": evidence_ids, "valid_json": True}


def prompt_for_case(case: dict) -> str:
    evidence = case.get("evidence_context") or []
    context = "\n".join(f"- evidence_id={item['id']}; page={item.get('page')}; text={item.get('text', '')}" for item in evidence if item.get("id"))
    if not context:
        context = "（没有可用证据；必须拒答，evidence_ids 返回空数组。）"
    return ("你是证据优先的财务问答助手。只能依据下面提供的证据回答。\n"
            "只返回一个合法 JSON 对象，不要 Markdown。格式："
            '{"answer": "...", "evidence_ids": ["证据ID"]}。\n'
            "evidence_ids 只能填写实际使用的证据 ID，不能猜测或编造。\n"
            f"证据上下文：\n{context}\n问题：{case['question']}")


def execute_condition(provider, cases: list[dict], dual: bool, price_per_1k: float) -> dict:
    rows = []
    for case in cases:
        started = __import__("time").perf_counter()
        calls = 2 if dual else 1
        responses = []
        error = None
        for _ in range(calls):
            try:
                responses.append(provider.generate(prompt_for_case(case)))
            except ModelProviderError as exc:
                error = str(exc)
                break
        tokens = sum(r.token_usage.get("input", 0) + r.token_usage.get("output", 0) for r in responses)
        text_ok = bool(responses and all(r.text.strip() for r in responses))
        parsed = parse_model_output(responses[-1].text) if responses else {"answer": None, "evidence_ids": [], "valid_json": False}
        gold_ids = set(case.get("gold_evidence_ids", []))
        returned_ids = set(parsed["evidence_ids"])
        rows.append({"case_id": case["id"], "question": case["question"], "gold_answer": case.get("answer"), "gold_evidence_ids": sorted(gold_ids), "model_text": responses[-1].text if responses else None, "parsed_answer": parsed["answer"], "returned_evidence_ids": parsed["evidence_ids"], "evidence_hit": bool(gold_ids & returned_ids), "valid_json": parsed["valid_json"], "status": "success" if error is None and text_ok and parsed["valid_json"] else "failed", "failure_reason": "provider_error" if error else (None if text_ok and parsed["valid_json"] else "invalid_output"), "duration_ms": round((__import__("time").perf_counter() - started) * 1000, 2), "token_count": tokens, "error": error})
    durations = sorted(r["duration_ms"] for r in rows)
    failures = sum(r["status"] != "success" for r in rows)
    tokens = sum(r["token_count"] for r in rows)
    return {"evidence_hits": sum(row["evidence_hit"] for row in rows), "hits": None, "total": len(rows), "evaluated": len(rows), "failure_count": failures, "failure_rate": failures / len(rows) if rows else None, "p50_latency_ms": durations[len(durations) // 2] if durations else None, "p95_latency_ms": durations[max(0, int(len(durations) * .95) - 1)] if durations else None, "cost_usd": tokens / 1000 * price_per_1k, "results": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/evals/week17-llm-comparison.json")
    parser.add_argument("--execute", action="store_true", help="allow configured real provider; no API key is read from files")
    parser.add_argument("--confirm-real-run", action="store_true", help="required together with --execute")
    parser.add_argument("--max-cases", type=int, default=0, help="explicit maximum number of cases; required for real runs")
    args = parser.parse_args()
    settings = ModelSettings.from_env()
    if args.execute and not args.confirm_real_run:
        raise SystemExit("real runs require --confirm-real-run")
    if args.execute and settings.provider == "fake":
        raise SystemExit("--execute requires MODEL_PROVIDER=openai-compatible")
    if args.execute and not settings.api_key:
        raise SystemExit("real runs require MODEL_API_KEY from the process environment")
    if args.execute and args.max_cases <= 0:
        raise SystemExit("real runs require --max-cases > 0 to cap spend")
    budget_usd = float(os.getenv("LLM_EVAL_BUDGET_USD", "0"))
    if args.execute and budget_usd <= 0:
        raise SystemExit("real runs require LLM_EVAL_BUDGET_USD > 0")
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
        "safety": {"max_cases": args.max_cases if args.execute else None, "budget_usd": budget_usd if args.execute else None, "api_key_source": "process_environment_only"},
    }
    if args.execute:
        provider = OpenAICompatibleProvider(api_key=settings.api_key, model=settings.model, base_url=settings.base_url, timeout_seconds=settings.timeout_seconds)
        cases = load_cases("data/evals/golden_questions.jsonl", args.max_cases)
        price = float(os.getenv("LLM_EVAL_PRICE_USD_PER_1K_TOKENS", "0"))
        result["status"] = "measured"
        result["dataset_split"] = "development"
        result["conditions"] = {"single_agent": execute_condition(provider, cases, False, price), "dual_agent": execute_condition(provider, cases, True, price)}
        result["metrics"] = {"hits": None, "total": len(cases), "p50_latency_ms": None, "p95_latency_ms": None, "failure_rate": None, "cost_usd": sum(v["cost_usd"] for v in result["conditions"].values())}
        result["limitations"] = ["Quality hits remain null until evidence IDs are independently scored.", "Real provider results require human review of model evidence."]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
