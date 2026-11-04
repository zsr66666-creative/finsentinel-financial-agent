# FinSentinel

面向消费电子行业的财报与公告证据链风险研判工作台。

> 当前仓库处于 v0.1 规划与开发阶段。演示数据、真实语料和评测结果会明确标记；项目不提供投资建议、交易信号或收益承诺。

## 项目目标

FinSentinel 将公司财报、公告、结构化指标和人工复核连接成可追溯工作流：

`来源文档 → 指标/证据 → 规则与 Agent 分析 → 复核 → 评测回归`

首版聚焦消费电子/电子制造行业的 5 家上市公司、年度分析和三类风险：盈利能力变化、存货/应收账款/现金流异常、重大公告事项。

## 目录

- `backend/`：FastAPI、SQLAlchemy、数据工具和工作流
- `frontend/`：Next.js/React/TypeScript 研究工作台
- `data/`：公司清单、来源元数据、评测候选和示例；原始 PDF 与完整语料不提交
- `docs/`：架构、数据契约、评测和 16 周路线
- `experiments/fastgpt/`：FastGPT 对照实验记录

## 本地启动

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATA_MODE = "synthetic_demo"
uvicorn app.main:app --reload --port 8000
```

API 文档：<http://localhost:8000/docs>

### 前端

```powershell
cd frontend
npm install
npm run dev
```

默认前端地址：<http://localhost:3000>

复制 `frontend/.env.example` 为 `.env.local`，再按需设置后端地址。

### 真实资料模式

真实资料需要先通过官方来源采集脚本生成本地语料，并设置 `DATA_MODE=real_corpus` 与 `CORPUS_PATH`。仓库默认不上传 PDF、完整提取文本、索引或向量库。上传前请核对来源许可。

## 状态说明

- `synthetic_demo`：虚构演示数据，仅用于开发和页面联调。
- `real_corpus`：带来源 URL、披露时间、页码和 SHA-256 的本地真实资料。
- 未测量的准确率、Recall、延迟和成本显示为 `N/A`，不会把目标值当作成绩。

## 开源与限制

代码采用 MIT License。第三方数据、PDF、模型和依赖遵守其各自许可。项目用于学习和研究辅助，不构成证券投资建议。详见 `docs/implementation-roadmap.md`、`DATA_LICENSE.md` 和 `SECURITY.md`。
