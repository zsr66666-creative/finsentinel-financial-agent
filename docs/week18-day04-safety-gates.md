# v0.2 Week 2 Day 4：真实评测安全门槛

真实 Provider 评测不会因为脚本参数而意外产生费用。必须同时满足：

```powershell
$env:MODEL_PROVIDER = "openai-compatible"
$env:MODEL_API_KEY = "从密码管理器临时注入"
$env:LLM_EVAL_BUDGET_USD = "5"
python experiments/week17_llm_comparison.py --execute --confirm-real-run --max-cases 10
```

安全规则：

- API Key 只从进程环境读取，不从文件读取；
- `--execute` 必须配合 `--confirm-real-run`；
- 必须设置正数 `--max-cases` 限制题数；
- 必须设置正数 `LLM_EVAL_BUDGET_USD`；
- 未满足任一条件时立即退出，不写入真实结果；
- dry-run 默认保持离线，质量、延迟和成本为 `null`。
