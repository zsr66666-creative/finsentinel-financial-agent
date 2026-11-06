# 第十一周 Day 1：Next.js 数据交互基线

## 已验证能力

- 多公司列表通过 `/api/v1/companies` 加载。
- 预警列表通过 `/api/v1/alerts` 加载。
- 公司指标通过 `/api/v1/companies/{company_id}/metrics` 加载。
- 页面支持公司、风险等级、关键词和人工复核状态筛选。
- API 请求有超时、异常处理和离线演示回退。
- 空告警、空指标和无证据状态均有明确空状态。
- 人工复核提交失败时保留原状态并显示错误提示。

## 验证结果

```text
npm test
4 passed

npm run build
Next.js production build passed
```

## Day 1 结论

当前前端已经具备第十一周数据交互基线，后续重点转向证据可视化、加载状态细化和真实 API 联调。
