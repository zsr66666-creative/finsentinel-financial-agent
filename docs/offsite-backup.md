# Windows Encrypted Backup Pull

This setup keeps a daily encrypted copy of the newest verified FinSentinel recovery point on a Windows computer. ECS keeps at most seven encrypted exports. Windows keeps at most seven verified copies. The Windows computer must be on and connected at the scheduled time; a login trigger retries after missed runs.

The SFTP account is public-key-only, chrooted, and exposes a read-only SFTP view restricted to `/exports`. The Windows client pins the SSH host key, checks the SSH-protected index and ciphertext SHA-256, then streams age decryption into the recovery archive verifier. Plaintext is never written to disk. ECS 导出成功不能证明 Windows 已拉取；操作页面只报告 ECS 服务和本机恢复检查。

## Before ECS Installation

1. Install age and Python 3.12 on Windows. Ensure `age.exe`, `age-keygen.exe`, `ssh-keygen.exe`, `sftp.exe`, and `python.exe` are on `PATH`.
2. Generate an age identity on Windows with `age-keygen -o "$env:USERPROFILE\finsentinel-age-key.txt"`; protect the file so only your Windows account can read it. Before calling disaster recovery complete, create a second protected copy on a separate device and verify both copies with `age-keygen -y`.
3. Create a dedicated SSH key pair with `ssh-keygen.exe -t ed25519 -N '' -C finsentinel-windows-backup-pull -f "$env:USERPROFILE\.ssh\finsentinel-backup-pull"`. Keep the private key on Windows. Transfer only the `.pub` public key to the ECS console as `/root/finsentinel-backup-pull.pub`, mode 600.
4. On ECS, get the SSH host public key and fingerprint using `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. Compare the fingerprint over the trusted ECS console. Copy that public host key to the Windows known_hosts file as `120.24.108.60 <key-type> <base64-key>`; do not derive trust from an unauthenticated network scan.
5. Allow inbound TCP/22 in the Alibaba Cloud security group only from the Windows public IPv4 address with `/32`. If that address changes, update the rule.

## ECS Install

Upload and verify the source package as described in the release instructions. Run its installer as root only after verifying the package checksum:

```bash
set -euo pipefail
package=/root/finsentinel-windows-offsite.tar.gz
echo '<published-sha256>  '"$package" | sha256sum -c -
target="$(mktemp -d /root/finsentinel-windows-offsite-XXXXXXXX)"
tar -xzf "$package" -C "$target"
bash -n "$target/deploy/ecs/install-operations-offline.sh"
bash "$target/deploy/ecs/install-operations-offline.sh"
```

The installer preserves the current root SSH effective settings and rolls back its managed SSH block if acceptance fails. After it succeeds, configure only the public age recipient in `/etc/finsentinel/offsite-export.env`:

```bash
set -euo pipefail
recipient='age1replace-with-the-public-recipient-derived-on-Windows'
[[ "$recipient" =~ ^age1[0-9a-z]{8,100}$ ]]
sed -i "s/^FINSENTINEL_AGE_RECIPIENT=.*/FINSENTINEL_AGE_RECIPIENT=$recipient/" /etc/finsentinel/offsite-export.env
chown root:root /etc/finsentinel/offsite-export.env
chmod 600 /etc/finsentinel/offsite-export.env
systemctl start finsentinel-ops-backup.service
journalctl -u finsentinel-ops-backup.service -n 30 --no-pager
```

The journal should show an `encrypted_export: ok export_verified` result. This means only that ECS published a verified encrypted export. It does not confirm a Windows pull. Do not remove any age private-key copy from ECS until the Windows identity and separate offline copy have both been opened and their derived public recipients match this configuration.

## Windows Setup with Task Scheduler

From an elevated PowerShell window only if required to install dependencies, ensure the listed tools are available. Run `deploy/windows/install-offsite-task.ps1` from the extracted source package in your normal user session. The script checks the pinned host key and age identity, creates a daily task plus a logon retry, and prints the public key that must be installed on ECS before the first pull. If you generated that key after the ECS package was installed, copy its `.pub` line to the console and rerun the ECS installer only through the approved release flow; do not edit the root account's `authorized_keys`.

After the SFTP public key is installed and the security-group `/32` rule is active, run the task once:

```powershell
Start-ScheduledTask -TaskName FinSentinel-OffsitePull
Get-ScheduledTaskInfo -TaskName FinSentinel-OffsitePull
Get-Content "$env:LOCALAPPDATA\FinSentinel\pull-status.json"
```

Success requires `status` to be `ok` and reason `verified`; check that a `.tar.gz.age` and matching `.json` exist in `%USERPROFILE%\FinSentinelBackups`. Before treating disaster recovery as accepted, restore a downloaded backup into a disposable test database. Do not paste the age identity, SSH private key, or decrypted backup into chat.

## Production Acceptance Record

As of 2026-11-18, the following live checks have passed:

- The Windows Task Scheduler task `FinSentinel-OffsitePull` runs daily at 04:00 Beijing time and retries after a missed run at the next logon. The reported latest run completed with task result `0`; the local status recorded `status=ok` and `reason=verified`.
- A real encrypted ECS export was downloaded to Windows. The client checked the index size and SHA-256, decrypted the stream in memory, and verified the archive manifest, `COMPLETE` marker, file hashes, and source references.
- The dedicated SFTP account's write probe was rejected; SSH command execution was rejected with the SFTP-only service message. The ECS SSH host key was pinned using its console-verified Ed25519 fingerprint. The user confirmed the inbound TCP/22 security-group source is the current Windows public IPv4 `/32`.
- A Windows-downloaded encrypted backup was streamed through a one-time forced-command SSH receiver and restored to a strictly named temporary PostgreSQL test database. ECS reported `restore_verified`; a subsequent check found no leftover restore database, uploaded archive, or one-time authorized key. The production database was not the restore target.

These checks establish that this backup could be decrypted, verified, and restored into an isolated test database. They do not establish full-machine recovery, geographic separation, or row-by-row independent verification beyond the backup system's manifest, schema, table-count, and artifact-reference checks.

## Remaining Key Risk

The user has deferred making a second independent age private-key copy. The Windows identity is readable and has been used for a successful restore drill. The age identity was originally generated on ECS before being provisioned on Windows; whether that original ECS private-key file still exists has not been checked. Do not claim that ECS contains only the public recipient until that is verified, and do not remove any remaining ECS private-key copy until an independent second copy has been created and its derived public recipient has been checked. If the Windows device and every other private-key copy are lost, retained ciphertext cannot be decrypted.

## Routine Checks and Recovery

- Task status: `Get-ScheduledTaskInfo -TaskName FinSentinel-OffsitePull`.
- Local status: `%LOCALAPPDATA%\FinSentinel\pull-status.json`.
- Local verified ciphertext: `%USERPROFILE%\FinSentinelBackups`.
- ECS export status: `journalctl -u finsentinel-ops-backup.service`; this is separate from Windows pull status.
- A failed pull leaves previously verified Windows copies in place. Resolve network, host-key, age, disk, or account errors, then run the scheduled task again.
- Keep a second age identity copy on a separate device. Keep at least one ciphertext copy outside both the ECS and the Windows computer for geographic separation.
- Repeat the restore drill periodically in a disposable isolated environment; retain the result and clean up only the drill's own temporary test database and one-time authorization.
