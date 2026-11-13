# Task 7：真实问题向量与云端候选证据

## 实现与边界

`/compare` 在原有金额核对之后新增独立的候选证据面板，导入本地 `scripts.vector_query export` 生成的单问题 JSON，再请求同源 Task 6 API。问题、模型、前缀、公司、报告期和向量绑定，校验 512 维、有限数值与归一化；不接受编辑问题后继续复用旧向量。支持加载、超时、接口错误、空结果、降级提示、物理页码和来源哈希。候选排名不是置信度，也不成为已复核金额结论。

此版本为“本地编码 → 网页导入 → 云端检索”，**尚未实现网页自由输入后自动在线编码**。ECS 继续不安装 PyTorch、不加载模型；查询包及源向量包保留在忽略的 outputs 目录。来源标识只显示文本，不把 local:// 链接当公网 PDF 下载链接。

## 本地真实编码与云端验收

在仓库根目录运行（本地须已有缓存模型及 sentence-transformers）：

```powershell
python -m scripts.task7_query_acceptance --base-url http://120.24.108.60
```

输出 `outputs/task7-queries/` 下 4 个单问题查询包、原始接口响应和 report。网页可直接导入 `parent-direct.json` 等文件。自定义问题可沿用：

```powershell
python -m scripts.vector_query export --file outputs/task7-queries/custom.json --question "立讯精密母公司期末应收账款是多少？" --company 002475 --period 2026H1
```

2026-11-14 实测 `data/evals/task7-cloud-query-smoke.json`：固定 BGE 修订 `7999e1d3359715c523056ef9478215996d62a620`；真实问题单独编码，不复制数据库向量。4 题均来自已知应收账款证据，2 题直接表述、2 题同义表述；公司 002475、期间 2026H1、云端候选全集 14 条，RRF 每路深度 20，Top-5：

| 方法 | 命中 / 题数（每题单个黄金片段） |
|---|---|
| BM25 | 2/4 |
| 向量 | 4/4 |
| RRF | 4/4 |

这是已知来源的开发冒烟验收，不是独立测试集，不用于调参；不支持泛化准确率、完整财报覆盖、缺证据拒答或财务结论正确性声明。云端耗时是顺序单次请求样本，不报告稳定的 p95；本地模型加载及编码耗时单独记录。

## 验收状态

- 本地：17 项前端测试、TypeScript 检查通过。Windows 默认构建被子进程 EPERM 阻断；临时线程模式编译和类型检查通过，但静态生成 DataCloneError，未作为生产构建通过证据。
- 云端：现有 Task 6 API 已接受 4 道真实自然语言查询向量，模型、公司、期间、PDF 指纹及无降级状态检查通过。
- Task 7 网页部署、生产构建与浏览器交互：等待执行部署脚本后验收，不能用旧网页 HTTP 200 替代。
- 部署只替换前端，沿用现有同源 API、standalone 资源同步、历史静态文件保留及回退机制，不开放 8000 端口。
