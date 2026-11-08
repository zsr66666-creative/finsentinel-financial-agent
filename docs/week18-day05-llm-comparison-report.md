# v0.2 Week 2 LLM 对照报告

状态：`adapter_only`

## 条件结果

| 条件 | 命中数 | 总题数 | 失败率 | p50 ms | p95 ms | 成本 USD |
|---|---:|---:|---:|---:|---:|---:|
| deterministic_baseline | 40 | 59 | 0.0 | None | 3.05 | 0.0 |
| single_agent | 40 | 40 | 0.0 | 18.39 | 20.93 | 0.0 |
| dual_agent | 40 | 40 | 0.0 | 16.62 | 18.2 | 0.0 |

## 失败分类

`timeout`、`rate_limit`、`provider_4xx`、`provider_5xx`、`invalid_json`、`evidence_missing`、`period_mismatch`、`tool_error`、`other`。

## 限制

- Deterministic adapters only; no real LLM quality measurement.
- Synthetic fixture remains separate from real PDF golden set.
- No metric is considered measured when its value is null.
