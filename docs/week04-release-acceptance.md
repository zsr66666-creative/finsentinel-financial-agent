# 限定证据比较上线与验收记录

记录日期：2026-11-12（北京时间）。依据用户粘贴的服务器输出和明确反馈整理；不是本轮直接登录服务器所得。

| 项目 | 状态 | 证据或边界 |
| --- | --- | --- |
| 四条真实向量补齐、重复导入、读回 | 用户反馈通过 | 用户回复“都没问题”；未提供完整导入输出 |
| 后端 b84d2d1 部署 | 通过，有输出 | git 更新、health connected/postgresql、母公司 supported |
| 合并比较 | 通过，有输出 | claim_true=false，difference=-772501509.62，两条 p60 证据 |
| 缺口径拒答 | 通过，有输出 | needs_review，claim_true=null，evidence_ids=[] |
| 服务器经公网 IP/Nginx 请求 | 通过，有输出 | 母公司未增加 true，difference=-306502051.55，p63 数值及 p62 标题 |
| 前端 09d476c 生产构建 | 通过，有输出 | 编译、类型检查、静态生成完成，含 /compare |
| standalone 切换 | 通过，有输出 | 3000 探测通过，旧构建保留 |
| /compare 页面访问 | 用户反馈通过 | 用户明确反馈两种访问均能打开；不是交互验收 |
| 浏览器母公司按钮及结果 | pending | 尚无明确操作结果或截图 |
| 浏览器合并按钮及结果 | pending | 尚无明确操作结果或截图 |
| 浏览器缺口径及旧结论清除 | pending | 尚无明确操作结果或截图 |
| 浏览器网络失败、手机布局 | pending | 尚未验收 |

备份目录（用户输出）：`/opt/finsentinel-releases/20261112-014006/previous-next`。保留备份；恢复流程尚未实际演练。最初 Nginx 127.0.0.1/compare 返回 404，后续使用站点 Host 并由用户确认可访问；不据此声称任何 Host 均可用。

全站 /health 仍标 synthetic_demo；本接口结果为 reviewed_real_pdf。只支持指定财报、明确日期/口径、应收账款增加/未增加的有限语法。不是通用财报问答，也不证明查询 embedding 或向量召回被此接口使用。

## 开发边界用例

`scripts/week04_comparison_boundary_eval.py` 使用私有 scope4 包作为本地证据，新增 13 个已知契约开发检查：两种口径、允许表达、未支持同义词、缺口径/冲突、未复核/无效日期、其他公司、双重否定、未来预测、缺标题及缺数值。预期拒答仅表示边界保护正确，不表示这些问题可以回答。

```text
PYTHONPATH=backend;.
python -m scripts.week04_comparison_boundary_eval --package outputs/vector-batch/scope4.json --output data/evals/week04-comparison-boundary.json
```

用例由当前实现知情编写，不是独立测试集，禁止据此宣称泛化准确率。未调整语法或检索参数。后续新增真正独立题集需另行标注来源与冻结协议。

## 待人工确认

在公网浏览器执行：母公司未增加 true，差额 -306502051.55 元，62/63 页；合并增加 false，差额 -772501509.62 元，60 页；删除口径后待复核且旧数值结论消失。收到明确反馈后才能更新对应 pending 项。本轮仅记录与评估，不需重新构建或重启网站。
