# FinSentinel

面向上市公司财报的证据研究门户：查找原文、核对期间金额、记录人工复核，并导出可追溯的研究报告。

> 已部署至阿里云 ECS，当前功能推进至 Task 12。真实报告、来源校验、人工复核与合成演示数据明确分开；项目用于研究辅助，不构成投资建议、交易信号或收益承诺。

## 能做什么

- **研究门户**：从实际索引生成公司库、报告库、行业筛选和覆盖范围；每家公司有独立研究页。
- **原文检索**：输入问题，使用 CPU ONNX 编码、BM25 与 pgvector 排序融合检索候选片段，保留公司、报告期、物理页码和来源哈希。
- **财务核对**：对限定报告中的营业收入、应收账款和经营现金流核验金额、单位、期间与报表口径，用 Decimal 计算差额及变化率。
- **人工复核**：确认、驳回、需要补充证据；决策与来源快照指纹绑定，保存追加历史，支持幂等提交和并发冲突检查。
- **我的研究（本次开发）**：按账号保存公司、证据快照与私人备注，记录研究入口，历史问题预填后可重新执行。
- **研究报告**：下载 Markdown 或 JSON，包含原始期间、精确金额、原文定位、PDF 哈希和当前复核状态。
- **演示工作台**：保留监控、规则与 Agent 分析、告警反馈、评测和数据质量工具，合成样例不作为真实财务结论。
- **界面**：分组侧栏、独立功能页、浅色/暗色/跟随系统、移动导航，以及管理员创建的真实账号、昵称和头像设置。

研究流程：

`官方报告采集 → 来源与哈希核验 → 选页解析与索引 → 候选检索 / 固定财务契约核对 → 人工复核 → 报告导出`

检索排名不是置信度，检索命中不等于金额正确；来源校验通过也不等于已完成人工复核。

## 真实数据覆盖

| 公司 | 当前报告范围 | 可用研究能力 |
| --- | --- | --- |
| 立讯精密（002475） | 2024FY 官方年报；2026H1 本地 PDF 证据 | 选页/片段检索；2026H1 应收账款的限定问题比较 |
| 三七互娱（002555） | 2024FY 官方年报 | 选页检索；合并口径三项财务比较、复核与导出 |
| 科大讯飞（002230） | 2024FY 官方年报 | 选页检索；合并口径三项财务比较、复核与导出 |

- 行业已从电子制造扩展至互联网游戏与人工智能；领域标签不表示经过审核的“高新技术企业”资格。
- 实际覆盖以 `/api/v1/evidence/scopes` 返回的报告、物理页码及片段数为准，**选页索引不是全文覆盖**。未来企业或报告不作为现有数据展示。
- Task 11/12 财务核对仅覆盖两家公司、2024FY 合并口径的六个固定指标契约；不支持的公司、期间或口径不会回退到演示金额。
- 立讯 2026H1 为保留的本地 PDF 证据路径，不能与官方在线采集的年报混称为独立核验的官方下载。详见[既有比较接口](docs/week04-comparison-api.md)。
- 原始 PDF、模型权重、数据库、向量和凭据不随代码仓库分发；克隆仓库不等于获得生产真实语料。

## 页面分区

| 路径 | 用途 |
| --- | --- |
| `/` | 研究入口、实际目录统计和公司列表 |
| `/companies`、`/companies/{code}` | 公司库及独立公司研究 |
| `/reports` | 报告库、覆盖页码及来源标识 |
| `/evidence` | 按公司/报告期检索候选原文 |
| `/compare` | 既有立讯精密限定证据比较 |
| `/workbench`、`/workbench/{section}` | 演示监控、告警、复核、评测、数据质量和演示公司库 |
| `/my-research` | 私人公司/证据收藏、备注及研究历史 |
| `/login`、`/settings` | 真实账号登录、昵称与头像设置 |
| `/admin/operations` | 管理员运维状态、备份与恢复检查摘要 |

## 架构

| 层次 | 技术与职责 |
| --- | --- |
| 前端 | Next.js 15、React 19、TypeScript、CSS；同源 API，standalone 生产构建 |
| API | FastAPI、Pydantic、SQLAlchemy；明确来源、范围和错误状态 |
| 数据库 | 生产 PostgreSQL + pgvector；SQLite 用于本地演示及部分测试 |
| 检索编码 | 固定修订 BAAI/bge-small-zh-v1.5，512 维；独立 CPU ONNX 查询编码服务 |
| 采集 | 管理员鉴权 API、持久任务队列、单 worker、租约及恢复、内容身份去重 |
| 财务证据 | 固定来源契约、PDF/文本哈希、页码/单位/期间/口径校验、精确十进制计算 |
| 复核 | 独立追加记录、快照指纹、幂等键与乐观并发检查；不同于演示告警反馈 |
| 部署 | Ubuntu ECS、Nginx、systemd；源码离线包、构建后切换、数据库备份与失败回退 |

数值核对不依赖生成式模型输出；已有 Agent/模型工作流与真实来源校验的状态分别标注。架构背景见 [architecture.md](docs/architecture.md)。

## 本地启动

以下命令在仓库根目录执行，示例为 Windows PowerShell，使用 Python 3.11+、Node.js 22。

### 后端

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e './backend[dev]'
$env:DATA_MODE = 'synthetic_demo'
python -m uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

API 文档：[localhost:8000/docs](http://localhost:8000/docs)；健康检查：[localhost:8000/health](http://localhost:8000/health)。生产数据库额外安装 `./backend[postgres]` 依赖。

### 前端（另一个终端）

```powershell
Copy-Item frontend/.env.example frontend/.env.local
cd frontend
npm ci
npm run dev
```

打开 [localhost:3000](http://localhost:3000)。示例配置指向 `http://localhost:8000`；演示登录接受任意非空账号和密码，不是真实身份认证。昵称/头像保存在浏览器本地，演示会话使用 sessionStorage。

本地演示模式可使用 `/workbench` 的合成数据。研究首页、公司库和报告库只显示实际索引，不用演示数据补齐；未配置真实语料时可能为空或明确报错。SQLite 快速启动不包含生产的 pgvector、编码器、PDF 或复核表迁移，不能据此宣称完成真实检索部署。完整真实链路参见下方部署及任务文档。

### 检查

```powershell
python -m pytest backend/tests/test_task12_reviews.py backend/tests/test_task11_financials.py backend/tests/test_persisted_comparison.py backend/tests/test_migrations.py backend/tests/test_week13_review.py -q -p no:cacheprovider
cd frontend
npm test
npx tsc --noEmit
npm run build
```

上述为针对近期改动的检查，不代表整个后端测试集。Windows 如遇 Node 测试子进程权限限制，可用 `node --test --test-isolation=none tests/*.test.mjs`；`spawn EPERM` 不算构建成功，生产构建需另行验证。缺少本地官方 PDF 时，相关测试会跳过，云端验收会直接核验正式产物。

## 阿里云部署与验收

当前采用 Nginx 对外提供前端与同源 API；后端 `8000` 和编码器端口保持回环监听，不直接开放公网。基础部署文档为[原生 ECS 部署与回退](docs/ecs-native-deployment.md)，其中早期验收记录是历史快照；近期真实链路以各任务文档和对应源码包为准。

Task 12 更新现有服务器：

```powershell
# 本地，从已提交的版本生成源码包
python -m scripts.package_task12 --output finsentinel-task12-review.tar.gz
```

上传包至服务器后，先用打包输出的 SHA-256 校验，再解压到新目录，执行 `bash -n deploy/ecs/install-task12-offline.sh` 和安装脚本。**该脚本用于已有 Task 8–11 环境的升级，不是空白服务器一键安装器**；需要已有数据库、官方 PDF、编码器、systemd 服务、npm 与后端测试依赖（含 pytest）。

安装器先验证源码清单、运行测试与构建，再备份数据库、执行增量迁移和临时 PostgreSQL schema 内的并发验收，最后切换前后端并检查页面/资源。失败回退旧服务配置和前端；已提交的增量表及记录保留，不用整库恢复覆盖用户数据。离线包不需要 GitHub 拉取，但 npm 安装仍需依赖缓存或 registry 网络。

**最近一次 Task 12 验收证据（用户提供的 ECS 输出及浏览器反馈）：**

- 源码版本 `c49dffab135c9f01c67b5a3407b4096d2caae543` 已部署，前端 33 项测试和生产构建通过。
- 本地针对性后端检查 34 项通过；服务器选择的后端测试通过，另有 4 项因未携带本地 PDF 测试夹具而跳过，后续正式产物检查覆盖六个真实财务指标。
- 迁移 `005_financial_reviews`、PostgreSQL 隔离并发与新连接持久化检查通过，临时 schema 已清理。
- 两家公司 JSON/Markdown 导出、未授权写入拒绝、旧比较接口，以及 16 个页面和静态资源检查通过。
- 向量仍为 **1050 条**，该次验收未改动向量；正式复核记录为 **0 条**，自动测试没有伪造生产人工决定。这些数量仅代表该次验收快照。
- 用户确认页面展示与报告下载正常；正式人工复核提交、真实身份认证、HTTPS 和长期运行稳定性不因此视为已验收。

## 当前边界与下一步

- 已实现[管理员创建的真实账号与权限](docs/real-accounts.md)，**阿里云账号升级及浏览器角色验收待执行**；升级前线上仍为演示登录。新增复核绑定服务器用户，历史自报署名保留；应用追加历史不是外部防篡改审计账本。
- 账号模式启用后复核写入使用登录会话和复核员/管理员权限，不再接受维护口令；旧版本兼容模式保留原独立令牌。真实密码只在 HTTPS 提交，升级时 HTTP 应用入口跳转 HTTPS，保留 ACME 验证路径。
- 复核记录与金额及来源快照绑定，来源改变不沿用原确认；来源不可用时不以旧记录补造数值。
- 测试/冒烟验收不等于独立金融评测。未测量的准确率、召回率、延迟和成本不作为已取得成绩展示。
- [免费公网 IP HTTPS 与自动续期](docs/free-ip-https.md)已完成服务器签发、本机受信 TLS、模拟续期和用户浏览器访问确认。真实账号升级仍待部署；更多公司/报告与全文覆盖需独立采集和验收。

## 文档与目录

| 位置 | 内容 |
| --- | --- |
| `backend/`、`frontend/` | API、证据/复核服务与研究门户 |
| `scripts/`、`deploy/ecs/` | 来源核验、验收、源码打包与 ECS 部署 |
| `data/` | 来源清单、元数据及示例，非完整生产语料 |
| `docs/` | 架构、数据契约、历史实验与实施记录 |
| `experiments/fastgpt/` | FastGPT 对照实验记录 |

- [Task 9：真实报告索引与覆盖范围](docs/task9-corpus-expansion.md)
- [Task 10：互联网游戏与人工智能企业接入](docs/task10-company-corpus.md)
- [Task 11：来源绑定财务比较](docs/task11-financial-comparison.md)
- [研究门户布局与验收](docs/research-portal-ui-acceptance.md)
- [Task 12：真实财务复核与报告导出](docs/task12-financial-review.md)
- [实现路线](docs/implementation-roadmap.md)、[发布检查清单](docs/release-v0.1-checklist.md)、[历史变更](CHANGELOG.md)

## 开源与许可

代码采用 [MIT License](LICENSE)。第三方数据、PDF、模型和依赖遵守其各自许可，生产材料不随源码分发。详见 [DATA_LICENSE.md](DATA_LICENSE.md) 与 [SECURITY.md](SECURITY.md)。

## 运维备份与监控

新增管理员只读运维页、每日本机数据库及原始产物备份、每周隔离数据库恢复验证和五分钟健康检查。保留最近七个验证完整的备份点，失败任务不清理已有恢复点。配置和备份仅由 root 读取；网页不提供备份下载。此功能尚待 ECS 部署验收，本机同盘备份不属于异地容灾。部署、检查范围及恢复限制见 [operations.md](docs/operations.md)。

个人研究保存与隔离规则、部署及人工验收见 [personal-research.md](docs/personal-research.md)。本次功能需完成服务器部署与浏览器验收后才记为上线。
