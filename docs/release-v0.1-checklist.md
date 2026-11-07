# v0.1 开源发布检查清单

## 发布前必须完成

- [ ] `git status` 干净，远程 `main` 与本地提交一致。
- [ ] CI backend 通过：依赖安装、导入检查、pytest。
- [ ] CI frontend 通过：`npm ci`、`npm test`、`npm run build`。
- [ ] README 启动命令可复制执行。
- [ ] 架构图、数据许可、贡献规范和安全边界已提交。
- [ ] 评测报告写明命中数/总题数、数据集、语料版本、运行时间和代码版本。
- [ ] synthetic fixture 与真实 PDF 黄金集没有混合计分。

## 发布时明确说明

- 默认 `DATA_MODE=synthetic_demo`，页面中的公司、数字、页码和证据是合成样例。
- 真实资料需要用户自行下载并核对官方来源和再分发许可。
- 未配置真实 LLM provider；确定性适配器结果不能代表真实模型质量。
- Docker/Podman 若无法拉取镜像，只能记录环境阻塞。

## 推荐命令

```powershell
git status --short --branch
git log -1 --oneline
git push origin main
```
