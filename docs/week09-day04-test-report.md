# Week 09 Day 4 测试验证记录

## 验证范围

运行了不依赖临时文件的核心测试：

```text
python -m pytest backend/tests/test_financial_calculations.py backend/tests/test_event_rules.py backend/tests/test_risk_rules.py backend/tests/test_retrieval.py backend/tests/test_week7_8_retrieval_eval.py -q
```

结果：

```text
26 passed
```

## 结论

财务计算、风险规则、公告事件规则、检索和第七至第八周评测逻辑通过。

完整测试套件中的部分测试使用 `tmp_path`，当前 Windows/Codex 环境对 pytest 临时目录和 `.pytest_cache` 有权限限制。该问题属于执行环境，不能作为业务测试通过或失败来解释。用户本机 CMD 应在清理临时目录后运行：

```cmd
set PYTEST_ADDOPTS=--basetemp=%CD%\\.pytest-tmp -p no:cacheprovider
python -m pytest backend\\tests -q
```

## 运行纪律

- 不把权限错误计入业务失败；
- 不把 26 个核心测试通过扩大表述为完整测试套件通过；
- 完整套件最终结果以用户本机运行输出为准。
