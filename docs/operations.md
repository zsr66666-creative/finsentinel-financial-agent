# 本地备份与运行监控

## 范围

管理员 `/admin/operations` 展示关键服务、数据库、受信本机HTTPS、磁盘、证书、最近备份/恢复验收及异常历史。页面仅可读取和刷新，不提供执行命令、恢复生产库或下载敏感文件的入口。
每日本机恢复点会尝试生成 age 加密导出，供 Windows 通过只读 SFTP 每日拉取。ECS 导出日志不代表 Windows 已收到副本；配置与验收见[Windows 异地备份操作指南](offsite-backup.md)。
本机HTTPS成功不能证明公网安全组或用户网络正常；外部通知渠道本期未接入。

截至2026-11-18，Windows 定时拉取、只读账号约束和一次真实异地备份隔离恢复演练均已完成验收。Windows 端拉取状态不写回 ECS，也不显示在管理员运维页；应在 Windows 本机检查 Task Scheduler 结果和 `pull-status.json`。独立 age 私钥副本尚未准备，ECS 是否残留早期生成的 age 私钥也待核实，故不宣称具备完整密钥灾备。具体证据和边界见[Windows 异地备份操作指南](offsite-backup.md)。

## 计划任务

| 任务 | 时间 | 管理单位 |
| --- | --- | --- |
| 每日备份 | 北京时间03:30，随机延迟不超过5分钟 | finsentinel-ops-backup.timer |
| 隔离恢复验收 | 每周日北京时间04:30，随机延迟不超过5分钟 | finsentinel-ops-restore.timer |
| 运行检查 | 每5分钟 | finsentinel-ops-check.timer |
| 加密导出 | 随每日本机备份执行（需配置 age 公钥） | finsentinel-ops-backup.service |

使用systemd，错过每日/每周任务后补执行；同类备份恢复互斥。首次部署先备份并实际恢复到独立测试库，成功后启用定时任务。检查任务失败或长时间未更新时，页面不能显示正常。

## 文件与权限

- `/var/backups/finsentinel`：root专用0700；恢复点文件0600，包括数据库dump、引用原始资料、清单与受限配置归档。含账号哈希、研究数据和可能的服务凭据，禁止上传GitHub或发到聊天。
- `/var/lib/finsentinel/operations/private`：root专用任务结果，不通过API返回。
- `/var/lib/finsentinel/operations/status.json`：root写、finsentinel组只读；只含固定检查摘要与最多200条状态变化。
- `/etc/finsentinel/offsite-export.env`：root专用配置，只含 age 公钥 recipient 和受限 SFTP 导出路径，不放私钥。
- `/srv/finsentinel-sftp/finsentinel-backup-pull/exports`：供 chroot SFTP 只读账号访问的加密导出目录；不放明文恢复点。
- API `/api/v1/admin/operations`：仅认证管理员可读，未登录401，非管理员403；未启用账号模式也不允许匿名访问。

ECS 和 Windows 各保留最近7个成功受管加密恢复点。新副本没有完成校验时不清理旧成功副本。未知文件或符号链接不自动删除，空间不足会记录失败。数据保留政策只针对各自专用目录，不会清理旧应用发布目录或用户数据。

## 恢复验证的含义

备份在导出的数据库快照中记录表计数，核对数据库引用的原始文件与SHA256。恢复验收先检查清单完整性，再将dump恢复到严格命名的专用测试数据库，核对schema及计数和文件引用，最后清理此次创建的测试库。
不覆盖线上库、不写入正式人工复核、不重启采集worker。计数/schema验收不等于逐行校验或完整应用灾备演练。若原始文件缺失，则不发布为完整成功恢复点；需要补齐正确原件后重试，不能用网页可显示替代原文件验证。

## 阈值

证书剩余不足48小时警告，不足24小时严重；证书续期timer启用不等于续期成功。
最近成功备份超过30小时警告、超过48小时严重；恢复验证超过8天警告。首次缺失显示未知。
异地导出按每日本机备份任务执行；Windows 拉取成功时间在 Windows 本地状态文件检查。ECS 检查页不将导出误报为 Windows 收件成功。根磁盘剩余低于20%或4GiB警告，低于10%或2GiB严重。状态文件超过15分钟未更新显示严重。异常变化和恢复写入有界历史，同一状态不反复追加。

## 运维查看

```bash
systemctl list-timers 'finsentinel-ops-*' --no-pager
systemctl show finsentinel-ops-backup.service -p Result -p ExecMainStatus
journalctl -u finsentinel-ops-backup.service -n 30 --no-pager
journalctl -u finsentinel-ops-restore.service -n 30 --no-pager
systemctl start finsentinel-ops-check.service
```

oneshot任务执行完通常为inactive，用Result、退出码和最近成功时间判断，不单凭is-active。无需把完整日志和受限备份公开；发送排查输出前确认不含口令、Cookie、私钥或环境文件内容。

需要手动触发备份时在可信服务器控制台执行 `systemctl start finsentinel-ops-backup.service`；恢复验收为 `systemctl start finsentinel-ops-restore.service`。这是独立测试库验证，不是恢复生产库的操作命令。

## 发布与验收

源码包不含生产数据、PDF、模型或私钥；包含installer与清单，先校验发布SHA256。构建与测试在发布目录完成，再切换后端/前端；既有账号、Cookie规则、HTTPS/Nginx、worker和encoder保留。
失败时恢复旧应用配置/前端与受管timer状态；保留成功备份、诊断及状态文件，不自动回滚整个生产数据库。
初次服务器验收包括真实备份、隔离恢复、状态任务、受保护API拒绝匿名、页面/静态资源受信TLS检查和服务状态。
随后管理员浏览器登录并访问运行状态页，确认可刷新且信息准确，普通账号访问被拒绝。尚无服务器输出或浏览器确认时，只报告已实现/CI通过。
