import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    summary_path = root / "data/evals/week17-comparison-summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {"conditions": []}
    report = {
        "report_id": "week17-llm-comparison-report-v1",
        "status": summary.get("status", "not_run"),
        "code_version": summary.get("code_version"),
        "generated_at": summary.get("generated_at"),
        "dataset": {"path": "data/evals/golden_questions.jsonl", "split": "development", "corpus_version": "week10-multi-company-v3"},
        "conditions": summary.get("conditions", []),
        "failure_analysis": {"categories": ["timeout", "rate_limit", "provider_4xx", "provider_5xx", "invalid_json", "evidence_missing", "period_mismatch", "tool_error", "other"], "rows": []},
        "limitations": summary.get("limitations", []) + ["No metric is considered measured when its value is null."]
    }
    (root / "data/evals/week17-llm-comparison-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# v0.2 Week 2 LLM 对照报告", "", f"状态：`{report['status']}`", "", "## 条件结果", "", "| 条件 | 命中数 | 总题数 | 失败率 | p50 ms | p95 ms | 成本 USD |", "|---|---:|---:|---:|---:|---:|---:|"]
    for item in report["conditions"]:
        lines.append(f"| {item.get('condition')} | {item.get('hits')} | {item.get('total')} | {item.get('failure_rate')} | {item.get('p50_latency_ms')} | {item.get('p95_latency_ms')} | {item.get('cost_usd')} |")
    lines += ["", "## 失败分类", "", "`timeout`、`rate_limit`、`provider_4xx`、`provider_5xx`、`invalid_json`、`evidence_missing`、`period_mismatch`、`tool_error`、`other`。", "", "## 限制", "", *[f"- {x}" for x in report["limitations"]]]
    (root / "docs/week18-day05-llm-comparison-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("report generated")


if __name__ == "__main__":
    main()
