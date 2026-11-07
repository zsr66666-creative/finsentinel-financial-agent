# Week 16 Day 1：可复现交付基线

## 目标

让新同学能够区分合成演示、真实语料和已验证结果，并按 README 启动项目。

## 已核对的交付物

- `README.md`：后端、前端、健康检查和真实资料模式启动说明。
- `compose.yaml`：后端健康检查、前端依赖和端口映射。
- `.github/workflows/ci.yml`：Python 3.12 后端测试、Node 22 前端测试和构建。
- `docs/architecture.md`：数据、工作流、复核和评测关系图。
- `docs/week15-evaluation-report.md`、`docs/week14-agent-comparison.md`：评测边界和结果记录。
- `docs/week15-day04-fixes.md`：用户反馈到修复的回归记录。

## 本地复现

```powershell
# 后端
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATA_MODE = "synthetic_demo"
$env:PYTHONPATH = "."
python -m pytest -q
uvicorn app.main:app --reload --port 8000

# 新终端启动前端
cd frontend
npm ci
npm test
$env:NEXT_PRIVATE_BUILD_WORKER = "1" # Windows 若出现 spawn EPERM
npm run build
npm run dev
```

## CI 验收

GitHub Actions 会在 Ubuntu 上执行完整后端导入、pytest、前端测试和生产构建。CI 通过才可将 v0.1 标记为可复现交付。

## 当前限制

- 本机 Podman/Docker 镜像拉取受网络环境影响，Compose 端到端不能在所有 Windows 环境宣称已验证。
- 真实 LLM provider 未配置；第十四周对照实验使用确定性适配器。
- 浏览器视觉验收和真实用户试用仍需人工完成。
- 评测结果必须区分真实 PDF 黄金集与 synthetic fixture，不能混合计分。
