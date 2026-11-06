# Week 11 数据质量接口修复

## 问题

前端请求 `/api/v1/data/quality`，后端原先只提供 `/api/v1/data-quality`，导致页面数据质量状态请求返回 404。

## 修复

为现有质量处理函数增加 `/api/v1/data/quality` 兼容路由，同时保留原 `/api/v1/data-quality` 路径，避免已有客户端受影响。

## 验证

- 新增 API 回归测试，确认嵌套路由返回 `200`、`data_mode` 和公司数量字段。
- 后端测试：`50 passed`。
