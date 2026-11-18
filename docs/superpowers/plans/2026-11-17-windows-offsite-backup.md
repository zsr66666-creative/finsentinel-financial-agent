# Windows Pull Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep seven verified age-encrypted FinSentinel recovery points on ECS and pull them daily to the user's Windows computer over a read-only, host-key-pinned SFTP account, without staging plaintext archives.

**Architecture:** Reuse the current verified local backup and age streaming encryption. Replace the Google Drive transport with an atomic ECS export directory exposed through a dedicated chrooted SFTP account, plus a standard-library Windows pull client that checks the index and ciphertext, streams age output into the archive verifier, then atomically retains seven verified ciphertext copies. Remove the misleading Google upload health state; ECS records export outcomes in its journal while the Windows client reports actual pulls locally.

**Tech Stack:** Python 3.12 standard library, pytest, age, OpenSSH internal-sftp, systemd, Windows OpenSSH `sftp.exe`, Windows Task Scheduler, PowerShell 5.1 setup script.

## Global Constraints

- Google Drive and rclone are not part of the Windows pull design; at completion no OAuth token or age private key is stored on ECS, in Git, task arguments, logs, or chat. Remove any existing ECS age-key copy only after the Windows and separate offline copies are confirmed readable and derive the configured recipient.
- ECS may encrypt only the newest directory returned by `valid_backups` after a fresh `verify_backup` call.
- ECS export and Windows retention are each limited to seven managed encrypted archives and their indexes; cleanup happens only after a newer archive is fully verified and atomically published.
- Windows stores ciphertext only; age plaintext is streamed into `verify_archive` and never written to a file.
- The SFTP account is key-only, read-only, chrooted, has no shell or forwarding, and cannot read the local backup root; existing root SSH and application services remain intact.
- SSH ingress is restricted in the Alibaba Cloud security group to the Windows public IPv4 `/32`; the host key is pinned and changed/unknown keys fail closed.
- A possible ECS private-key copy is removed only after the Windows copy and a separate offline copy are each opened and both derive the configured public recipient.
- Local backup/restore status remains distinct from ECS export status and Windows pull status; neither ECS UI nor logs may claim a Windows pull succeeded.
- No paid storage or external storage API is introduced.

---

### Task 1: Allow streaming archive verification

**Files:**
- Modify: `scripts/verify_offsite_archive.py`
- Modify: `backend/tests/test_operations_offsite.py`

**Interfaces:**
- `verify_archive(source)` accepts either a filesystem path (existing behavior) or a readable binary stream; it returns the existing verified metadata result and raises bounded `ValueError` codes on invalid input.
- CLI remains `python scripts/verify_offsite_archive.py <archive-path>` and retains its existing JSON output contract.

- [ ] Add path-parity and binary-stream tests using `io.BytesIO` with the same valid archive fixture; assert both return identical verification metadata.
- [ ] Add stream failure tests for truncated gzip/tar input and malformed tar headers; assert `ValueError('archive_invalid')` and ensure no member is extracted.
- [ ] Refactor `verify_archive` to select `tarfile.open(name=source, mode='r|gz')` for path-like input and `tarfile.open(fileobj=source, mode='r|gz')` for a binary stream without closing a caller-owned stream.
- [ ] Run `python -m pytest backend/tests/test_operations_offsite.py -q -p no:cacheprovider`; expect all existing path-based tests and the new stream tests to pass.

### Task 2: Replace Google remote sync with verified ECS exports

**Files:**
- Modify: `scripts/operations_offsite.py`
- Modify: `backend/tests/test_operations_offsite.py`
- Modify: `scripts/operations_runner.py`
- Modify: `backend/tests/test_operations_runner.py`

**Interfaces:**
- `export_latest(backup_root, export_root, recipient, *, encryptor=None)` returns a bounded dictionary with `status`, `reason`, `backup_id`, `ciphertext_sha256`, and `ciphertext_size` on success; failures return fixed reason codes and do not mutate existing published exports.
- Each archive has a sibling index named `<archive filename>.json`; the client enumerates only strict index names, selects the lexicographically newest backup ID, then validates the downloaded index schema exactly: `{ "schema_version": 1, "backup_id": <strict backup id>, "filename": <strict managed filename>, "ciphertext_size": <positive integer>, "ciphertext_sha256": <lowercase SHA-256> }`.
- Existing `scripts.operations_backup.valid_backups`, `verify_backup`, and `_encrypt_backup` remain the source of recovery point validation and streaming encryption.

- [ ] Replace `FakeRemote`/rclone tests with filesystem-backed export tests for newest-valid-point selection, revalidation before encryption, encrypted output, exact index fields, atomic publication, seven-file retention, idempotent repeat export, and failure preservation.
- [ ] Add tests for symlinked export roots, unsafe filenames/index data, partial encryption output, index write failure, duplicate backup ID, and ensuring only strict managed archive/index pairs are pruned. Index filename is the archive filename plus `.json`; publish the index last so an unindexed archive is never selectable by the client.
- [ ] Implement `export_latest` with a root-owned export directory, a per-export lock, private temporary files, strict `OBJECT_RE` names, index SHA-256 and size, `fsync`, atomic archive rename followed by atomic index rename, then prune only after the new pair is published and revalidated. Remove only this invocation's unpublished archive if index publication fails. Repeated export of an identical backup ID is idempotent after revalidating its index and digest; a conflicting object fails closed. Reuse `_encrypt_backup` and never create a plaintext tar file.
- [ ] Update the `backup` runner path to call `export_latest` only after the local backup succeeds. Print only `encrypted_export: <status> <fixed-reason>`; keep the backup/restore API state about local backups only and do not write a `Windows pull succeeded` or equivalent ECS status.
- [ ] Run `python -m pytest backend/tests/test_operations_offsite.py backend/tests/test_operations_runner.py -q -p no:cacheprovider`; expect filesystem retention and local status behavior to pass without rclone or network credentials.

### Task 3: Expose exports through a restricted SFTP account

**Files:**
- Modify: `deploy/ecs/install-operations-offline.sh`
- Modify: `backend/tests/test_operations_delivery.py`
- Modify: `scripts/package_operations.py`

**Interfaces:**
- ECS path: `/srv/finsentinel-sftp/finsentinel-backup-pull/exports` is both the root-owned export directory and the SFTP-visible directory; no bind mount or writable SFTP view is needed.
- SSH account is `finsentinel-backup-pull`, key-only, locked/no-password, `nologin`, `ForceCommand internal-sftp -R`, `ChrootDirectory` root-owned, and `DisableForwarding yes`; its dedicated authorized-keys file is separate from `/root/.ssh/authorized_keys`.
- The installer creates/validates a root-owned SSH config backup and managed `Match User` block; `sshd -t` and `systemd-analyze verify` must succeed before reload/enable. On failure it restores the SSH config and managed export timer/service state.

- [ ] Add installer contract tests asserting the exact account, chroot, read-only SFTP, forwarding/TTY/password restrictions, independent authorized-key path, SSH syntax validation, rollback trap coverage, and absence of edits to Nginx/root authorized keys.
- [ ] Keep export in the existing root-owned daily backup service: invoke it only after the local backup has passed verification; do not add a separate timer or service that could export before a successful backup.
- [ ] Update the installer to create the chroot and export directory directly at the path above; keep the chroot and all parents root-owned/non-writable, the `exports` directory root-owned and non-writable by the account, and published files root-owned/readable. Do not add mount units or expose `/var/backups/finsentinel`.
- [ ] Read a dedicated Windows public key from a root-only operator input file or interactive prompt; reject empty, non-Ed25519/RSA-unsafe, malformed, or duplicate managed keys and never embed private key material in the package.
- [ ] Make SSH changes transactionally: save the original config/drop-in and managed timer/service state, validate candidate config using `sshd -t`, reload SSH, test localhost key-only SFTP, and restore prior state on any failed check without restarting or altering root SSH access. Bootstrap the Windows host pin by transferring the public host-key line from the ECS console, comparing its `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` fingerprint out of band, and only then saving it; never trust an unverified `ssh-keyscan` result.
- [ ] Update package allowlists and package tests so the new script, installer, units, docs, and tests are included while private keys, production exports, database dumps, PDFs, and OAuth files are excluded.
- [ ] Run `python -m pytest backend/tests/test_operations_delivery.py -q -p no:cacheprovider` and `bash -n deploy/ecs/install-operations-offline.sh`; expect source/package contract tests and shell syntax validation to pass.

### Task 4: Build a fail-closed Windows pull client

**Files:**
- Create: `scripts/windows_offsite_pull.py`
- Modify: `scripts/verify_offsite_archive.py`
- Create: `backend/tests/test_windows_offsite_pull.py`

**Interfaces:**
- `pull_latest(config, *, command_runner=subprocess.run, popen=subprocess.Popen)` downloads the index and its named ciphertext using Windows OpenSSH SFTP batch mode with `StrictHostKeyChecking=yes`, a fixed `UserKnownHostsFile`, a dedicated key, and a strict timeout.
- `verify_archive(binary_stream)` is consumed directly from `age -d` stdout. The pull client waits for age and verifier completion and rejects either nonzero result.
- Client configuration contains only server IP, username, remote export directory, host-key file, SSH key file, age identity path, and local ciphertext directory; secret contents are read from files, never command-line text.

- [ ] Create tests using temporary fake `sftp.exe`/`age.exe` commands or injected runners for strict remote listing parse/newest-index selection, successful pull, interrupted SFTP, oversized/malformed index, path traversal in filename, unexpected size/hash, wrong age identity, corrupt manifest, duplicate backup ID, and both child-process exit codes.
- [ ] Add retention tests proving seven newest verified managed archives are kept, a failed candidate never replaces or deletes the previous good copy, unmanaged files remain untouched, and cleanup cannot escape the configured local directory.
- [ ] Implement SFTP listing with one-name-per-line output; accept only index filenames matching the managed archive name plus `.json`, choose the greatest fixed-format backup ID, download that index, and verify its filename agrees with the contained backup ID. Bound index parsing to 16 KiB, validate ID/size/hash, verify ciphertext byte count and SHA-256, preflight free space, and use private staging files within the destination directory. Promote with `os.replace` only after the streamed archive verifier accepts the decrypted bytes.
- [ ] Connect `age -d -i <identity>` stdout to `verify_archive` as a binary stream; run verification in a worker thread while the main thread enforces the age process timeout, redirect stderr to a null sink, check both age exit status and verifier outcome, and terminate the child if verification fails. Never use age's `-o` option or create a plaintext temporary path.
- [ ] Write a bounded local status record containing timestamp and fixed success/failure code only; do not log key paths, archive contents, or subprocess stderr.
- [ ] Run `python -m pytest backend/tests/test_windows_offsite_pull.py backend/tests/test_operations_offsite.py -q -p no:cacheprovider`; expect all fake transport and failure-path assertions to pass on Windows and Linux.

### Task 5: Configure daily Windows scheduling and operator documentation

**Files:**
- Create: `deploy/windows/install-offsite-task.ps1`
- Modify: `docs/offsite-backup.md`
- Modify: `docs/operations.md`
- Modify: `backend/tests/test_operations_delivery.py`

**Interfaces:**
- PowerShell setup registers a daily Task Scheduler task plus an AtLogOn trigger for the current user, with interactive-token execution and `StartWhenAvailable` so a missed run starts at next logon.
- The task invokes the packaged Python pull client and reads the current user's OpenSSH private key, pinned host-key database, and age identity from explicit local paths.
- The guide documents one-time identity/key setup, two independent age private-key copies, SSH host-key pinning, ECS public `/32` rule, first pull, task/log verification, failure recovery, and the seven-day catch-up limit.

- [ ] Add delivery tests asserting the PowerShell task is user-scoped, interactive, daily plus logon-triggered, uses missed-run catch-up, and does not place private key contents or passwords in arguments.
- [ ] Implement the installer script with parameterized ECS IP and local directory defaults; refuse to overwrite existing private keys/host pins, create restrictive local ACLs for the backup directory and age identity, register/update only the named FinSentinel task, and provide a command to inspect its last result.
- [ ] Rewrite `docs/offsite-backup.md` for Windows SFTP pulls. Remove Google OAuth/rclone authorization, quota, and Drive troubleshooting steps; include exact non-secret Windows and ECS commands and explain that ECS export success is not proof of a Windows pull. Update `docs/operations.md` to remove active `/etc/rclone` and Drive status instructions.
- [ ] Add a documented/manual gate to compare `age-keygen -y` output from Windows and the offline copy with the configured recipient before instructing the operator to remove any ECS private-key copy; do not automate the removal.
- [ ] Run `python -m pytest backend/tests/test_operations_delivery.py -q -p no:cacheprovider`; inspect the PowerShell task XML in a Windows test or export mode without registering a production task.

### Task 6: Remove the obsolete Google Drive health surface

**Files:**
- Modify: `scripts/operations_runner.py`
- Modify: `backend/app/operations.py`
- Modify: `backend/tests/test_operations_runner.py`
- Modify: `backend/tests/test_operations.py`
- Modify: `frontend/src/lib/operations.mjs`
- Modify: `frontend/src/app/admin/operations/page.tsx`
- Modify: `frontend/tests/operations.test.mjs`
- Modify: `scripts/package_operations.py`
- Modify: `deploy/ecs/install-operations-offline.sh`

**Interfaces:**
- `/api/admin/operations` reports local backup, restore, and service checks only; it contains no `offsite_backup` row and does not infer Windows transfer state.
- ECS journal records encryption/export outcomes under a fixed safe prefix. Windows task status remains local to Windows.

- [ ] Add backend and frontend tests asserting no `offsite_backup` mandatory row, no Drive-specific reason labels, and no claim that server export means Windows received a copy.
- [ ] Remove Google Drive result parsing and `OFFSITE_*` OAuth environment use from `scripts/operations_runner.py`; retain a fixed export result line in the backup unit journal without storing it as a Windows success state.
- [ ] Remove offsite check labels/reasons from `backend/app/operations.py`, update the operations check count and sanitization tests, and remove the “异地加密备份” group and Drive-specific explanatory copy from the admin operations page.
- [ ] Remove the old Google Drive spec from `scripts/package_operations.py`'s operations package manifest and include the Windows pull spec; verify package source archives contain no obsolete rclone dependency setup.
- [ ] Run `python -m pytest backend/tests/test_operations.py backend/tests/test_operations_runner.py backend/tests/test_operations_delivery.py -q -p no:cacheprovider` and `node --test frontend/tests/operations.test.mjs`; expect the local backup/restore and service status tests to pass without an offsite API row.

### Task 7: Package, deploy, and perform live recovery acceptance

**Files:**
- Modify: `scripts/package_operations.py`
- Modify: `backend/tests/test_operations_delivery.py`
- Modify: `docs/offsite-backup.md`
- Modify: `deploy/ecs/install-operations-offline.sh`

**Interfaces:**
- The source-only deployment archive includes the new exporter, verifier, Windows client/setup, tests, and updated guide; `PACKAGE_FILES.json` and `SOURCE_REVISION` are reproducible and exclude keys, exports, and production data.
- ECS deployment has a dry-run/preflight mode that validates the package, shell syntax, SSH config, and systemd units before any service reload; live acceptance is not reported until Windows has pulled and verified a real archive.

- [ ] Add an offline packaging test that builds the operations tarball, validates every manifest hash, verifies shell LF endings, and asserts no `.agekey`, private SSH key, ciphertext export, database dump, PDF, OAuth token, `.next`, or `node_modules` enters the package.
- [ ] Run `python -m pytest backend/tests/test_operations_backup.py backend/tests/test_operations_offsite.py backend/tests/test_windows_offsite_pull.py backend/tests/test_operations_runner.py backend/tests/test_operations.py backend/tests/test_operations_delivery.py -q -p no:cacheprovider`, `node --test frontend/tests/operations.test.mjs`, `bash -n deploy/ecs/install-operations-offline.sh`, and the package archive audit.
- [ ] Build the deployment tarball from the committed revision and provide its SHA-256 with exact ECS `sha256sum`, extraction, preflight, and install commands. Do not include the existing untracked `finsentinel-offsite-operations-a42cf90.tar.gz`.
- [ ] On ECS, preserve a pre-change backup; confirm the old Drive offsite flag is disabled and its status hook removed. Preserve `/etc/rclone/rclone.conf` in a root-only pre-change backup and remove it only after confirming no other server job uses it. Validate `sshd -t`, `systemd-analyze verify`, localhost root SSH, application services, and existing operations timers before/after install; roll back managed SSH/export changes if any acceptance fails.
- [ ] Configure the Windows public IPv4 `/32` in the Alibaba Cloud inbound security-group rule, register the current user's Task Scheduler task, and perform a first real pull. Check ECS export digest/size against the index and Windows local status, then confirm age streaming verification passed.
- [ ] Prove the SFTP account cannot get a shell, upload/rename/delete files, forward ports, or read outside its chroot; confirm the root SSH login and web/API services still work.
- [ ] Confirm both sides retain at most seven verified ciphertext/index pairs, force one failed pull and verify the previous local copy remains intact, then perform an isolated restore drill from the Windows ciphertext before declaring recovery acceptance.

## Plan Self-Review

- Spec coverage: verifier stream support (Task 1); verified ECS export/index/retention (Task 2); chrooted read-only SFTP and transactional SSH deployment (Task 3); Windows pull, host pin, ciphertext-only retention, and failure safety (Task 4); logged-in daily/missed-run Task Scheduler behavior and key custody (Task 5); removal of misleading ECS transfer claims (Task 6); offline package, live pull, security checks, and restore drill (Task 7).
- Placeholder scan: no TBD/TODO implementation steps are used; all test commands and target paths are explicit.
- Interface consistency: `export_latest` and `verify_archive(binary_stream)` signatures are fixed above and consumed by the runner and Windows pull client; index fields are fixed and validated by the client. The exporter writes directly to the chroot export directory, so no bind-mount ownership ambiguity exists.
