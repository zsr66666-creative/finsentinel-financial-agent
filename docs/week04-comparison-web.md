# 证据比较网页

入口：工作台侧栏“证据比较 · 真实财报”，独立路径 `/compare`。页面调用只读比较接口，提供母公司未增加/合并增加示例、自定义输入、加载/失败/待复核状态、两期原始金额及差额、口径和真实证据 ID 与物理页。无演示答案回退；标题和数值行分别列出，原始 PDF 尚无在线预览。页面明确与工作台演示数据区分。

API 地址沿用 NEXT_PUBLIC_API_URL；未设置时该页默认同源。生产构建应显式设为空字符串，经 Nginx `/api/` 访问，不能把 localhost:8000 烘焙进公网构建。限定问句和证据检查范围与后端相同。

本地 TypeScript noEmit 检查通过；现有前端测试用 `node --test --experimental-test-isolation=none tests/domain.test.mjs` 运行，10/10 通过。常规 npm test 与 npm run build 均因 Windows 子进程 spawn EPERM 失败；无生产构建通过或浏览器视觉验收声明。待服务器构建和人工验收；未直接操作线上服务。

服务器更新前先检查 git status、systemctl cat finsentinel-frontend，确认现有 standalone 启动路径。以部署服务用户构建，保留当前构建备份；成功后复制 `.next/static` 到 `.next/standalone/.next/static`，如有 public 则同步到 standalone/public，再重启前端。不要在构建失败时重启。该项目保持 standalone 配置，不应切回 next start。

验收：浏览器进入 /compare；两示例分别为 true/false；编辑为缺少口径问题返回待复核；不可用时显示错误且不保留旧结论；手机屏幕检查可读性。真实答案必须携带对应口径的标题及数值行证据。HTTP 200 不能替代这些人工验证。
