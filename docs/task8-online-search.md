# Task 8 在线自然语言证据检索

## 功能

POST /api/v1/evidence/search/text 接收 query/company_code/period/top_k；固定模型，不允许客户端提供服务地址、模型或向量。后台通过 loopback 8081 的单进程 ONNX Runtime FP32 服务编码，保留中文检索前缀、CLS、L2 与512 token截断；使用同一模型修订的数据库向量作BM25/RRF检索。公开服务不开放8081或8000端口。

/compare 新增在线问题输入框，范围明确为立讯精密2026H1已入库片段；保留高级选项中的本地查询包导入。结果仅候选，不输出生成式答案，不能用空结果断言完整报告没有披露。原金额比较接口保持原逻辑。

编码服务及API各限制一个正在编码的请求，忙碌429；连接/读取限时、服务错误503，无假向量或隐式回退。模型manifest验证ONNX和tokenizer哈希。独立venv只装onnxruntime/tokenizers/numpy等推理依赖，不装PyTorch；独立systemd服务 MemoryHigh384M、MemoryMax512M。

## 当前证据

本地ONNX数值/内存评估见task8-cpu-feasibility.md。新文本API真实编码集成已通过：本地文本API → 实际loopback ONNX进程 → 测试中继到现有阿里云vector API，Top5包含已知母公司应收款证据。见data/evals/task8-local-text-integration.json。该结果不代表新文本端点已在云端上线。

后端目标测试覆盖参数/模型/有限归一化向量、空问题、错误掩码、超时容量释放、并发拒绝、原vector和compare回归。前端既有测试及TypeScript单独验证。Windows构建仍有spawn EPERM限制，ECS生产构建为发布门槛；浏览器点击、移动和新接口云端验收未完成。

## 离线部署

模型与原始reference不提交公开GitHub；交付已校验的私有tar.gz，包含源代码、模型、MIT模型说明、源码版本和文件清单。阿里云控制台上传后运行deploy/ecs/install-task8-offline.sh。

脚本先检验Nginx、现有服务、内存余量及所有包文件；在隔离release构建前端，安装独立推理venv，再跑Linux原模型一致性/内存测量，峰值须不超过384MiB；再切换后端systemd drop-in与encoder服务。文本检索、原比较通过才切换前端，并验收Nginx五页、所有静态资源和同源文本接口。任何切换后失败恢复原后端覆盖、encoder服务及旧前端；生产数据只读，不迁移数据库、不改Nginx。

已实施但未远程验证：独立服务、文本API、前端表单、部署/回退脚本。待用户上传包并运行后，再确认云端生产构建、Linux内存和实际交互，不以本地结果替代。
