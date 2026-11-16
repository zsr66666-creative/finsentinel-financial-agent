# 私人研究报告保存与管理

用户已批准在报告阅读验收后实施本功能，默认交付阿里云部署。

## 范围与契约
现有公司财务研究报告支持即时导出，本轮将其保存成按账号隔离的不可变快照。在002555和002230的2024FY合并财务核对区增加保存入口；保存请求只接收company_code、period、statement_scope、title及可选question，不接受客户端金额、证据或复核状态。服务器重新执行现有来源验证与export_research，从服务器事实生成快照。问题只是用户备注，不自动推导其真假；不扩展LLM或新公司数值契约。

GET/POST /api/v1/me/research/reports；GET/DELETE /reports/{id}；GET /reports/{id}/export?format=json|markdown。登录身份由session绑定，所有查询包含owner_id，跨账号404，AUTH_ENABLED=false拒绝。沿用CSRF保护。最多200份/账号，标题1至120字符，问题最多1000字符，快照限制2MiB，分页最多100。保存后修改仅通过删除与重新保存；不覆盖历史快照。缺失数据保留needs_review，不伪造金额。

新增008_saved_research_reports显式迁移，账户外键、索引及schema检查；不在应用启动时迁移。复用现有export_research输出格式，冻结generated_at、来源和review状态，记录snapshot_sha256。每次导出只读保存快照，绝不重算当前状态。

## 界面
保留研究门户风格。我的研究新增研究报告tab，列表标题/公司/生成时间及打开、删除。独立/research-reports/[id]详情页，展示保存时快照说明、问题、金额、证据、物理页链接和复核记录，提供JSON/Markdown下载。账户切换中止并清空旧请求，错误可重试，删除显式确认。登录返回路径允许严格UUID详情。原文仍走登录阅读器。

## 上线与验收
先通过旧版可信ops备份和隔离恢复再显式迁移，失败只回滚前后端配置，新增表保留。不更改TLS、原件、索引和账号权限。源码离线包有SHA256及manifest。验证账号隔离、CSRF、拒绝客户端金额、快照冻结、精确导出、分页删除、迁移幂等、前端解析及生产构建；CI PostgreSQL持久化验收；服务器与浏览器验收独立标明。
