# Week 12 Day 2：端到端 API 联调验收

## 自动化覆盖

- 健康检查 `/health`。
- 告警 `/api/v1/alerts`。
- 公司 `/api/v1/companies`。
- 公司指标 `/api/v1/companies/{company_id}/metrics`。
- 数据质量兼容路由 `/api/v1/data/quality`。
- 缺失公司和指标请求返回明确 `404`。
- 合成模式响应保持 `data_mode=synthetic_demo`，不会伪装成真实材料。

## 浏览器人工验收清单

启动后端和前端后，页面应显示“数据服务已连接”和 `API ONLINE`。随后检查告警列表、公司切换、指标、证据卡片和人工复核队列。停止后端并刷新页面时，应显示离线演示提示；后端恢复后点击“刷新数据”应重新连接。
