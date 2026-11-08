# v0.2 Week 2 Day 1：真实 LLM 对照实验协议

## 目标

在相同题集、语料、Provider 配置、工具白名单和超时预算下比较确定性基线、单 Agent 和双 Agent。

## 冻结条件

- 默认只运行 development 集；test 集冻结后才可运行。
- 真实语料与 synthetic fixture 分开统计。
- 每组记录命中数/总题数，不只记录百分比。
- 记录模型、Prompt 版本、代码提交、运行时间、p50/p95、失败率和成本。
- dry-run 不产生质量、延迟或成本实测值，字段保持 `null`。

## 运行方式

```powershell
# 安全的协议检查，不调用外部模型
$env:PYTHONPATH = "backend"
python experiments/week17_llm_comparison.py

# 真实运行前必须显式配置，API Key 只来自进程环境
$env:MODEL_PROVIDER = "openai-compatible"
$env:MODEL_NAME = "your-model"
$env:MODEL_API_KEY = "<provided-outside-repository>"
$env:MODEL_BASE_URL = "https://api.openai.com/v1"
python experiments/week17_llm_comparison.py --execute
```

Day 1 只冻结协议和结果格式，尚未宣称真实 LLM 质量结果。
