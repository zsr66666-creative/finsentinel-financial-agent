# 第十三周复核事务与反馈闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成告警确认、驳回、修改的事务性复核闭环，并生成需人工审核的回归候选。

**Architecture:** 后端以追加式反馈记录和事务服务保证一致性；API 暴露统一反馈契约；前端复核队列读取持久化状态并提交反馈。反馈不会直接改变黄金评测标签。

**Tech Stack:** FastAPI、Pydantic、SQLite、现有前端测试和 pytest。

## Global Constraints

- `reject` 和 `modify` 必须有原因；`modify` 必须有修改内容。
- 反馈历史不可覆盖；重复请求必须幂等。
- 事务失败不得留下部分写入。
- 回归候选初始状态必须是 `pending_review`。
- 不伪造真实材料、答案或人工审核结果。

### Task 1: 现状审计与基线

**Files:**
- Create: `docs/week13-day01-audit.md`
- Test: `backend/tests/test_week13_feedback.py`

- [ ] 检查现有模型、存储、告警 API 和前端复核入口。
- [ ] 写入当前字段、缺口、测试基线和明确不改动范围。
- [ ] 为三种动作写接口契约测试骨架。

### Task 2: 反馈模型和状态转换

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_week13_feedback.py`

- [ ] 定义反馈动作、原因、修改内容、幂等键和回归候选状态。
- [ ] 定义 `pending_review -> confirmed/rejected/modified_pending_review` 转换。
- [ ] 为非法状态转换和字段缺失添加测试。

### Task 3: 事务反馈服务和 API

**Files:**
- Modify: `backend/app/store.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_week13_feedback.py`

- [ ] 实现单事务写入反馈、更新告警、创建候选。
- [ ] 实现幂等键重复返回原结果，不重复插入。
- [ ] 返回统一结构化错误和成功响应。

### Task 4: 历史和回归候选查询

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/store.py`
- Test: `backend/tests/test_week13_feedback.py`

- [ ] 提供告警反馈历史查询。
- [ ] 提供待审核回归候选查询或纳入现有复核数据接口。
- [ ] 测试刷新/重复读取不会改变历史。

### Task 5: 前端复核交互

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Modify: `frontend/src/lib/domain.mjs`
- Test: `frontend/src/**/*.test.*`

- [ ] 为确认、驳回、修改提供表单和原因校验。
- [ ] 显示提交中、成功、失败和离线状态。
- [ ] 重新加载后显示服务端复核状态及历史。

### Task 6: 回归与发布检查

**Files:**
- Create: `docs/week13-day06-regression.md`
- Create: `docs/week13-day07-freeze.md`

- [ ] 运行后端和前端测试、构建及 `git diff --check`。
- [ ] 记录通过数量、环境限制和未完成项。
- [ ] 冻结第十三周版本并验证远程提交。
