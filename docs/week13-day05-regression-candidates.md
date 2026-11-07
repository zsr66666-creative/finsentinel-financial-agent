# 第十三周 Day 5：回归候选与前端反馈契约

前端复核提交现在携带 `reason`、`modification` 和唯一 `idempotency_key`，与后端反馈契约一致。驳回和修订仍要求复核说明；修订会把说明放入结构化 `modification.comment`。

回归候选保留原告警 ID、错误分类、原因、修改内容和 `pending_review` 状态，供后续人工审核，不会自动进入黄金集。
