# 第十三周 Day 4：反馈历史与回归候选

已新增：

- `GET /api/v1/alerts/{alert_id}/feedback`：返回单条告警的追加式反馈历史；
- `GET /api/v1/review/candidates`：返回状态为 `pending_review` 的回归候选；
- 重复读取不会创建新记录，反馈和候选可在数据库重启后继续读取。

验证：Day 4 接口测试通过，覆盖幂等重复提交、历史数量和候选查询。
