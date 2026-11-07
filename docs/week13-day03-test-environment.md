# 第十三周 Day 3：pytest 临时目录修复

## 根因

`backend/pytest.ini` 曾将 pytest 的 `basetemp` 固定为仓库内 `.pytest-tmp`。该目录在 Windows/Codex 环境中已被权限锁定，pytest 在创建或清理 `tmp_path` 时触发 `PermissionError: [WinError 5]`。

## 修复

- 移除固定 `--basetemp=.pytest-tmp` 配置；
- 保留 `-p no:cacheprovider`，避免生成 `.pytest_cache`；
- 忽略 pytest 系统临时目录命名模式 `.pytest-of-*`。

pytest 现在使用系统临时目录，由 pytest 为每次运行创建和清理隔离目录。历史受保护目录不再被新运行使用。
