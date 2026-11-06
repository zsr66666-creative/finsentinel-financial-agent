# Week 12 Day 1：运行配置与真实 API 验收基线

## 完成内容

- 统一 Docker Compose 的前端 API 环境变量为 `NEXT_PUBLIC_API_URL`，与 Next.js 页面实际读取的变量一致。
- README 增加后端健康检查、前端连接状态和离线回退的启动验收步骤。
- 已确认数据质量接口兼容路径 `/api/v1/data/quality` 已由前一项修复提供。

## 验收命令

```cmd
python -m pytest backend\tests -q
cd frontend
npm test
npm run build
```

运行服务后检查：

```text
GET http://localhost:8000/health -> 200
GET http://localhost:8000/api/v1/alerts -> 200
GET http://localhost:8000/api/v1/companies -> 200
GET http://localhost:8000/api/v1/data/quality -> 200
```

页面连接成功时显示 `数据服务已连接` 和 `API ONLINE`；后端不可用时应显示离线演示提示，不能把合成数据标成真实材料。
