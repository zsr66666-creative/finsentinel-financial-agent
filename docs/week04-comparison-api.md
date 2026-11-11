# 限定证据比较接口

2026-11-12 状态更新：后端已部署，母公司、合并、缺口径及服务器经公网 IP/Nginx 请求已有用户提供的通过输出。下文“尚未部署”为实现时历史状态；当前状态及待验收项以 [上线记录](week04-release-acceptance.md) 为准。

POST `/api/v1/evidence/compare`，JSON 请求只允许 `question`（1–500 字）。

```json
{"question":"立讯精密2026年6月30日母公司应收账款较2025年12月31日是否未增加？"}
```

支持明确公司、两日期、母公司/合并口径的应收账款“是否增加/未增加”限定问句。仅接受已复核的 2026-06-30 对 2025-12-31 日期契约；其他情况返回 needs_review，不调用模型猜测。单位元来自已复核文件契约，并非自动从数据库文本推断。

读取现有 document_chunk_embeddings 中两条记录：数值行及对应标题。PostgreSQL 事务设置 READ ONLY；不生成 embedding、不迁移、不插入、不调用 LLM。检查记录唯一性、文本 SHA256、源 PDF SHA256、公司、报告期、文档 ID、物理页、口径、标题引用、已复核标题及两列数值。缺失或不一致返回 needs_review 和空 evidence_ids；数据库不可用返回 503，错误内容不暴露连接信息。

成功返回 supported、claim_true、difference、unit、两期数值、日期、口径及真实 evidence_ids（包含数值行和标题），附物理页。claim_true 表示所问命题是否成立：本样本“增加”为 false，“未增加”为 true，不等同于接口成功与否。

本地测试使用构造记录及 HTTP reader 替身；另用私有真实补齐包运行 compare_rows 检查两种口径。它们不等于真实 PostgreSQL 事务或阿里云 HTTP 验收。服务器四条记录导入/幂等/读回通过由用户反馈确认；本接口尚未在阿里云部署。

## 部署后验收

确认仓库无未处理更改后，在服务器更新代码、重启 backend（无需重建前端），检查 /health。随后执行：

```bash
curl --fail-with-body -sS http://127.0.0.1:8000/api/v1/evidence/compare -H 'Content-Type: application/json' --data '{"question":"立讯精密2026年6月30日母公司应收账款较2025年12月31日是否未增加？"}'
```

预期 supported、claim_true=true、difference=-306502051.55、unit=CNY，以及 p63-s4 与 p62-fulltext-line117 两条证据。还需检查合并口径、正向增加、缺少口径、未来日期及公网 Nginx 路径。未收到真实输出前保持远端验收 pending。网页尚未增加入口，不宣称任意问题或通用问答已完成。
