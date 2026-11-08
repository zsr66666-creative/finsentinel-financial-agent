# v0.2 Week 2 Day 2：单/双 Agent 运行器

## 已完成

- 复用第十四周冻结的共享 fixture 和确定性适配器；
- 新增统一运行脚本，分别执行单 Agent、双 Agent 条件；
- 输出 hit count、延迟和条件元数据；
- 明确标注 `adapter_only`，不把结果当真实 LLM 质量。

## 运行

```powershell
$env:PYTHONPATH = "backend"
python experiments/week17_agent_adapters.py
```

真实 Provider 评测需要单独配置 API Key、预算和人工批准，不在 CI 自动执行。
