# Windows Pull Backup Design

## Goal

Provide a zero-additional-cost copy of FinSentinel recovery points outside the ECS by having the user's Windows computer pull age-encrypted archives over SSH. Google Drive is not part of this design because both Windows and ECS timed out connecting to Google's OAuth and Drive API endpoints.

## Existing Contract

The daily ECS backup at `/var/backups/finsentinel` is root-only and contains verified recovery points with a `COMPLETE` marker, a manifest, a PostgreSQL dump, configuration archive, and referenced source PDFs. `scripts.operations_backup.verify_backup` validates these points. `scripts.operations_offsite._encrypt_backup` already streams a verified point through tar and age without staging a plaintext archive. The age private key is intended to be held by the user's Windows account and an independent offline copy; ECS needs only its public recipient. If a private-key copy currently remains on ECS, it must not be removed until both destination copies have been opened and their derived public key has been compared with the configured recipient.

## Architecture

After each successful daily local backup, a root-owned export job selects the newest verified recovery point, streams it through the existing age encryption path, and atomically publishes a uniquely named `.tar.gz.age` file plus a small JSON index containing the backup ID, ciphertext byte count, and SHA-256. It does not call rclone, Google, or any external storage API. It retains at most seven managed encrypted exports; failed encryption or verification leaves previous exports untouched.

ECS exposes only the encrypted export directory through a dedicated SSH account restricted to read-only SFTP in a chroot. The account uses a dedicated Windows public key, cannot obtain a shell, write files, forward ports, or access the backup root. SSH access remains limited by the ECS security group to the Windows network's current public IPv4 `/32`; changes to that address require updating the rule. Existing root SSH access and application services remain unchanged.

A Windows Task Scheduler task runs daily after the ECS backup/export window in the user's logged-in session, and is configured to run as soon as possible after a missed start when that user next logs on. A local script uses the pinned ECS SSH host key and the dedicated SFTP key to download the index and the named ciphertext into a staging file. It checks the expected name, byte count, and SHA-256, then streams age decryption into the existing archive verifier so plaintext is not written to disk. The verifier is extended to accept a binary stream as well as its existing path input; the client connects the age process stdout directly to this verifier and checks both process exit statuses. Truncated streams, malformed tar data, and nonzero age exit status fail closed. Only after internal manifest, `COMPLETE`, file hashes, and artifact references validate does it atomically promote the ciphertext into the local backup directory and prune older verified copies, keeping seven. The task records bounded success or failure status locally without credentials, plaintext paths, or token data.

## Failure and Retention Behavior

- A failed local backup creates no new export.
- A failed encryption, interrupted SFTP transfer, size/hash mismatch, decryption failure, or archive validation failure does not replace the last verified local copy or delete any existing copy.
- Server and Windows retention delete only files matching the strict managed filename pattern and only after a newer verified copy exists on the respective side.
- Windows offline or unreachable ECS causes the scheduled task to fail visibly and retry at the next scheduled/logon run. ECS retains seven exports, so a Windows outage longer than seven days can lose intermediate copies; it will still pull the newest retained export on return.
- The daily task is configured to run only in the user's logged-in Windows session so the age identity and local decryption validation use the intended profile. If the PC is off, asleep without task wake enabled, or the user is logged out at the scheduled time, the missed-run setting starts the task at the next logon.
- This protects against ECS disk/instance loss only when the Windows copy is on a different physical device. A second encrypted copy of the age private key must be stored offline; losing all private-key copies makes the archives unrecoverable.
- The administrator operations page continues to describe ECS local backup and restore status. Windows pull status is reported by Task Scheduler and a local bounded log; the ECS cannot claim that a client has pulled a file because the transfer account is read-only.

## Security Requirements

- ECS export creation accepts only the latest point returned by `valid_backups` and re-runs `verify_backup` immediately before encryption.
- The age private key remains on Windows and offline media; no private key or Google token is stored on ECS, in Git, task arguments, logs, or chat. Any existing ECS copy is removed only after the Windows copy and an independent offline copy are each confirmed readable and derive the configured public recipient.
- The SFTP chroot and all parent directories are root-owned and not writable by the export account. SFTP is forced read-only and the account has no shell or forwarding capabilities.
- The client pins the SSH host key, rejects unknown or changed keys, uses batch public-key authentication, and never falls back to passwords or broad security-group sources.
- Windows stores only ciphertext in its retained backup directory. Decryption validation is streamed to the verifier; plaintext archives are not staged on disk.
- Local retention runs only after validating the newly downloaded archive and never deletes files outside the managed directory or filename pattern.

## Acceptance

1. Unit tests prove export consumes only complete verified backups, uses streaming encryption, writes a strict manifest/index, and preserves prior exports on failure.
2. Tests prove SFTP configuration forces read-only chroot access, disables shell and forwarding, and rejects unsafe paths or symlinks.
3. The archive verifier accepts both filesystem paths and binary streams; tests cover truncated streams and malformed tar input. Windows client tests cover successful pull, interrupted transfer, bad size/hash, wrong age identity, corrupt manifest, duplicate backup ID, retention boundary, and preservation of the previous good copy on every failure. Tests also prove age plaintext is never written to a file and both subprocess exit statuses are checked.
4. ECS deployment validates `sshd -t` and systemd units before reload, records a pre-change backup, does not alter Nginx, application listeners, database, or current root SSH access, and rolls back the SSH drop-in and export timer if checks fail.
5. Live acceptance confirms one real existing backup is encrypted, pulled, and verified on Windows; the local ciphertext matches the announced digest; the export account cannot run commands or write; both sides retain no more than seven verified objects.
6. Live Windows acceptance confirms the Task Scheduler task runs in the user's logged-in session, can read the age identity, and starts after a missed run at the next logon while the ECS security-group source is restricted to the user's current public IPv4 `/32`.

## Explicit Limits

This costs no cloud storage fee but depends on Windows being powered on and online. If the computer is off or its public IP changes, pulls fail until the next run or security-group update. Seven server-side exports provide at most seven days of catch-up. The local copy is not geographically offsite unless the user also copies ciphertext to a removable device stored elsewhere. No real backup or recovery is considered accepted until the live pull, archive verification, and restore drill succeed.
