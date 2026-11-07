# 第十四周 Day 7：冻结记录

日期：2026-11-07

## 本周交付

- Day 1：实验协议和数据快照冻结；
- Day 2：确定性工具基线；
- Day 3：单 Agent 确定性 workflow 适配器；
- Day 4：双阶段独立复核适配器；
- Day 5：共享 40 条 approved synthetic fixture 可比题集；
- Day 6：对照实验 JSON 和 Markdown 报告。

## 冻结结果

实验题集：40 / 40 条可评分，全部为 `development` synthetic fixture。真实 PDF 黄金集 74 条、可评分 59 条，保持独立。

- 确定性工具：40 / 40；p95 2.68 ms；
- 单 Agent 适配器：40 / 40；p50 17.55 ms；p95 20.37 ms；
- 双 Agent 适配器：40 / 40；p50 17.70 ms；p95 23.03 ms；
- 三组超时：0 / 40；成本：0；
- 真实 LLM 单 Agent / 双 Agent：未测量，当前没有外部 provider。

## 结论

在当前简单合成事实题上，双阶段复核没有带来可观测质量提升，且 p95 略高。后续只应在复杂证据解释题和真实 LLM provider 可用时继续验证，不把本周结果写成双 Agent 优势。

## 验证

- 结果 JSON 已解析并校验命中数和分母；
- `git diff --check` 通过内容检查；
- 后端和前端基线测试在本周之前已通过；
- Windows 历史受保护目录仍可能产生 Git 扫描警告，但未进入提交。

## 版本

代码版本以本次提交 SHA 为准，推送后核对 `origin/main`。
