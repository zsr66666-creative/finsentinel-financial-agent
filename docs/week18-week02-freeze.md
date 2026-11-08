# v0.2 Week 2 冻结报告：Agent 对照实验基础

## 本周完成

- 冻结确定性基线、单 Agent、双 Agent 三组条件和统一字段。
- 新增单/双 Agent 适配器运行器。
- 新增命中数/总题数、失败率、p50/p95、成本和失败分类输出。
- 增加真实 Provider 运行安全门槛：确认参数、最大题数、预算和进程环境 API Key。
- 完成后端回归和适配器回归，结果写入 `data/evals/`。

## 当前可复现结果

```text
后端测试：69 passed
确定性基线：40 / 59
单 Agent 适配器：40 / 40
双 Agent 适配器：40 / 40
```

这些结果的状态是 `adapter_only`。它们验证运行器、证据链和报告格式，不是对真实 LLM 质量的测量。

## 冻结限制

1. 尚未配置真实 LLM provider 和 API 预算，因此没有真实模型命中率、成本或失败率。
2. synthetic fixture 与真实 PDF 黄金集严格分开，不能合并分母或宣称跨公司泛化。
3. 真实运行必须通过 `--confirm-real-run`、`--max-cases` 和 `LLM_EVAL_BUDGET_USD` 安全门槛。
4. 真实 LLM 结果必须保留 provider、model、Prompt、语料、代码版本和失败原因。

## 下一周入口

第 3 周开始 PostgreSQL 迁移：先保持 SQLite 本地模式，建立迁移脚本、索引和空库回归，再为 pgvector 做准备。
