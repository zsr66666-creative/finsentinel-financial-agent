# FinSentinel v0.1 架构

The v0.1 system uses a FastAPI service, SQLite, a Next.js workbench, deterministic financial tools, BM25 evidence retrieval and a bounded workflow. LangGraph and model providers are adapters added after the deterministic path is tested.

Data flow: official-source metadata and local documents enter the ingestion boundary; parsed pages and metrics enter the relational store; tools return typed values and evidence IDs; the workflow records every node and tool call; the frontend displays citations and review state.

```mermaid
flowchart LR
  UI[Next.js 工作台] --> API[FastAPI API]
  API --> DB[(SQLite / SQLAlchemy)]
  API --> WF[有界证据工作流]
  WF --> R[BM25 + 向量检索]
  WF --> Q[白名单财务计算]
  WF --> V[EvidenceVerifier]
  R --> CORPUS[带来源元数据的语料]
  V --> REVIEW[人工复核与反馈回流]
  REVIEW --> EVAL[评测与回归集]
```

## 边界

- `synthetic_demo` 只用于接口和页面联调，数字、公司、页码和证据均为合成数据。
- `real_corpus` 需要本地准备公开来源材料；仓库不提交原始 PDF、完整提取文本、索引或向量库。
- 工作流在证据不足、期间不匹配或工具参数错误时应停止或降级为待人工复核。
- 系统是研究辅助工具，不提供投资建议、交易信号或收益承诺。
