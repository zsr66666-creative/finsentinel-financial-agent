# Week 11 Day 3：多公司指标状态

## 完成内容

- 公司研究池继续支持多公司切换，并为每家公司独立加载指标。
- 增加指标加载中状态，避免切换公司时短暂显示上一家公司的指标。
- 增加指标接口失败提示和单独“重试”按钮。
- 保留真实接口空数据状态；离线模式继续明确使用合成样例。
- 增加指标状态映射函数测试，覆盖 loading、error、empty、has data 四种状态。

## 验证

- `frontend/npm test`：7 passed。
- `frontend/npm run build`：成功，Next.js 静态构建完成。
