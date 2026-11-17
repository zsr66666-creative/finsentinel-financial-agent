# Google Drive 异地备份

## 安全边界

异地副本使用 `age` 公钥加密，Google Drive 仅保存密文。age 私钥只保存在你的 Windows 电脑和另一份离线介质中；ECS 不保存私钥。Google OAuth 配置只放在 root-only 的 `/etc/rclone/rclone.conf`。部署包、网页状态、命令参数和聊天都不传递 OAuth token 或私钥。

此功能默认关闭，不购买配额。ECS 在发送前校验本机恢复点、检查远端可用容量、上传临时密文并回读比较 SHA-256；验证后才正式发布并保留最近 7 个受管对象。新对象上传或校验失败时不删除旧对象；本机备份仍保留成功记录，但异地任务会报失败。非本工具命名的远端文件不会被清理。

## Windows 生成并保管私钥

在 Windows 安装 age，并在 PowerShell 中运行：

```powershell
age-keygen -o "$env:USERPROFILE\finsentinel-age-key.txt"
age-keygen -y "$env:USERPROFILE\finsentinel-age-key.txt"
```

第二条命令输出以 `age1` 开头的公开 recipient。仅将 recipient 配置到 ECS；不要发送私钥文件或把它加入 Git。将私钥文件复制到独立离线介质，并确认两份都可读。建议限制 Windows 文件 ACL，仅允许你的账户访问。

## 配置 ECS

先在阿里云 ECS 控制台以 root 执行：

```bash
apt-get update
apt-get install --yes age rclone
install -d -o root -g root -m 700 /etc/rclone
rclone config --config /etc/rclone/rclone.conf
chmod 600 /etc/rclone/rclone.conf
```

在 `rclone config` 中创建名为 `drive` 的 Google Drive remote。若 ECS 没有浏览器，按 rclone 的交互提示在 Windows 上完成 `rclone authorize drive`，再把返回内容直接粘贴进 ECS root 控制台的交互提示。不要把授权内容放进命令参数、环境变量、shell 命令、部署包或聊天。完成后只验证远端名称和空间，不打印配置文件内容：

```bash
rclone about drive: --json
rclone mkdir drive:FinSentinel/offsite
```

部署会创建 `/etc/finsentinel/offsite.env`，默认内容为关闭状态。使用 `sudoedit /etc/finsentinel/offsite.env` 设置以下值；`OFFSITE_RECIPIENT` 填公开 recipient：

```ini
OFFSITE_ENABLED=true
OFFSITE_REMOTE=drive:FinSentinel/offsite
OFFSITE_RECIPIENT=age1替换为你的公开recipient
OFFSITE_RCLONE_CONFIG=/etc/rclone/rclone.conf
```

确保远端可用空间足以暂存 8 个当前恢复点大小的副本（7 个保留副本加一个待校验新副本）。免费空间受同一 Google 账号里其他数据占用影响，不保证一定足够。若额度未知或不足，系统拒绝异地上传，不会降低保留数，也不会删除本机恢复点。

```bash
chown root:root /etc/finsentinel/offsite.env /etc/rclone/rclone.conf
chmod 600 /etc/finsentinel/offsite.env /etc/rclone/rclone.conf
systemctl daemon-reload
systemctl start finsentinel-ops-backup.service
systemctl status finsentinel-ops-backup.service --no-pager
journalctl -u finsentinel-ops-backup.service -n 20 --no-pager
systemctl start finsentinel-ops-check.service
```

输出只应包含任务状态和固定错误码。不要贴出 rclone 配置、完整授权响应、环境文件内容或私钥。管理员随后打开 `/admin/operations`，在“异地加密备份”分区确认上传回读通过及最近成功时间。

## Windows 解密抽查

在 Windows 配置只读的 rclone remote 后下载一份 `.tar.gz.age` 密文到受限临时目录。然后用私钥解密：

```powershell
rclone copyto drive:FinSentinel/offsite/备份对象名.tar.gz.age "$env:TEMP\finsentinel-check.tar.gz.age"
age -d -i "$env:USERPROFILE\finsentinel-age-key.txt" -o "$env:TEMP\finsentinel-check.tar.gz" "$env:TEMP\finsentinel-check.tar.gz.age"
tar -tzf "$env:TEMP\finsentinel-check.tar.gz"
```

使用部署源码包中的 `scripts/verify_offsite_archive.py`（仅 Python 标准库），流式读取归档而不解压到文件系统，并校验安全路径、`COMPLETE`、manifest、每个文件大小与 SHA-256、所有 `artifact_refs`：

```powershell
python .\scripts\verify_offsite_archive.py "$env:TEMP\finsentinel-check.tar.gz"
```

只有输出 `"status": "verified"` 才算 Windows 解密抽查通过。随后安全删除临时明文、解密归档和下载密文。不要把解密文件上传到网盘或发到聊天。

## 失败排查与恢复限制

- `not_configured`：未启用，不影响本机备份。
- `quota_unknown` / `quota_insufficient`：检查 Google Drive 账号可用额度和 remote 授权；不删旧副本。
- `configuration_missing` / `configuration_invalid`：检查 root-only 环境文件和 rclone remote 是否存在，不要输出其内容。
- `upload_failed` / `remote_readback_failed` / `remote_integrity_failed`：检查网络、Google API 和服务日志中的固定错误码；旧副本保持不变。
- 若 OAuth 被撤销或 Google 账号丢失，异地副本可能不可用。Google 账号仍有能力删除自己的文件；该方案不抵御账号本身被接管。

灾难恢复时，必须先在 Windows 下载密文并确认私钥可用。只有受控维护窗口才短暂将私钥提供给新 ECS 解密；恢复后立即删除 ECS 私钥。先走既有隔离恢复验证，生产数据库恢复仍需管理员单独决定，不由自动备份验收执行。

## 验收状态

本地测试只验证加密流程契约、回读哈希、额度拒绝、错误保护和 7 份保留逻辑。真实 Google OAuth、实际可用免费空间、首次生产上传以及 Windows 私钥解密必须在你自己的账号和阿里云控制台完成；未取得脱敏回执前不标记为线上已验收。
