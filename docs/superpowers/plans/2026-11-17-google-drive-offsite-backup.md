# Google Drive Offsite Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in, age-encrypted copies of verified FinSentinel recovery points to a dedicated Google Drive folder, with remote verification and seven-copy retention.

**Architecture:** Keep the existing local backup and isolated restore flow. After a local recovery point passes `verify_backup`, stream a tar archive through `age` to `rclone`, verify the remote ciphertext by reading it back and comparing SHA-256, then prune only strict-name managed objects. A root-owned status record feeds a separate offsite check to the admin operations page; absent configuration remains `not_configured`.

**Tech Stack:** Python 3.12, PostgreSQL custom dumps, `age`, `rclone`, systemd, FastAPI, Next.js, Node/Python tests.

## Global Constraints

- Google Drive receives ciphertext only; no plaintext fallback.
- The age private key stays on the user's Windows computer and offline media; ECS stores only the public recipient.
- The rclone OAuth configuration is root-only and never appears in argv, logs, API output, Git, or chat.
- Keep at most seven verified remote recovery points; upload and verify a replacement before deleting any old point.
- Require free Drive quota sufficient for the pending copy and retained set; unknown or insufficient quota fails closed.
- Keep existing local backups and weekly isolated restore unchanged when offsite is not configured.
- Do not add production human review records or restore over the production database during acceptance.

---

### Task 1: Add the offsite transfer module

**Files:**
- Create: `scripts/operations_offsite.py`
- Create: `backend/tests/test_operations_offsite.py`

**Interfaces:**
- `sync_latest(backup_root, remote, recipient, rclone_config, *, runner=None)` validates the newest local recovery point and returns a bounded result containing `status`, `reason`, `finished_at`, `backup_id`, and `ciphertext_sha256`.
- The module uses argument arrays without a shell; all external command output is suppressed or mapped to fixed error codes.

- [x] Test strict remote object names, local manifest verification, quota failure, OAuth/config absence, failed encryption/upload/readback, retention ordering, and that every old remote object remains after an upload/readback failure.
- [x] Test that cleanup only targets strict-name objects under the configured dedicated remote directory and retains seven verified objects.
- [x] Run `python -m pytest backend/tests/test_operations_offsite.py -q -p no:cacheprovider` and confirm the new assertions fail only because the module/API is not implemented yet.
- [x] Implement streaming tar → age → rclone upload, bounded quota preflight, remote readback SHA-256 comparison, final naming, and post-verification retention cleanup.
- [x] Run `python -m pytest backend/tests/test_operations_offsite.py -q -p no:cacheprovider`.

### Task 2: Integrate backup jobs and read-only operations status

**Files:**
- Modify: `scripts/operations_runner.py`
- Modify: `backend/app/operations.py`
- Modify: `backend/tests/test_operations_runner.py`
- Modify: `backend/tests/test_operations.py`
- Modify: `frontend/src/lib/operations.mjs`
- Modify: `frontend/src/app/admin/operations/page.tsx`
- Modify: `frontend/tests/operations.test.mjs`

**Interfaces:**
- `OFFSITE_ENABLED=false` keeps the current local-only behavior; when true, `backup` also runs `sync_latest` and returns nonzero on remote failure without erasing local-success state.
- `check` adds one `offsite_backup` record with only fixed reason codes, last-success timestamp, and age status.
- The admin page adds an “异地备份” status group; unconfigured state is explicit.

- [x] Add tests that local success remains recorded when remote upload fails, old remote success metadata is preserved, offsite status becomes critical on failure, and unconfigured state is sanitized as `not_configured`.
- [x] Add frontend parser tests for the new mandatory status ID and safe metadata whitelist; assert no secret-like fields can pass through.
- [x] Run the targeted Python and Node tests and confirm the new assertions fail for the missing offsite integration/status contract.
- [x] Integrate offsite execution/status while preserving existing backup and restore behavior.
- [x] Run targeted Python and Node tests for operations status and the admin status parser.

### Task 3: Add deployment configuration and package contents

**Files:**
- Modify: `deploy/ecs/install-operations-offline.sh`
- Modify: `scripts/package_operations.py`
- Modify: `backend/tests/test_operations_delivery.py`
- Modify: `docs/operations.md`
- Create: `docs/offsite-backup.md`

- [x] Test that the committed package includes the offsite module, installer, recovery guide, and design spec, while excluding tokens, private keys, local backups, PDFs, and model files.
- [x] Run the new package assertions and confirm they fail because the offsite files/configuration are not included yet.
- [x] Extend installer to install/check Ubuntu `age` and `rclone`, preserve local timers, create root-only configuration paths, and configure offsite as disabled until the operator creates the dedicated Google remote and supplies a public age recipient.
- [x] Keep OAuth tokens out of command arguments, package manifests, diagnostics, and systemd status; use `/etc/rclone/rclone.conf` with root-only permissions.
- [x] Document Windows key generation/private-key custody, local rclone OAuth authorization, interactive ECS remote setup, quota preflight, first synchronization, failure checks, and Windows-side decrypt/hash validation.
- [ ] Run deployment/package tests, `bash -n deploy/ecs/install-operations-offline.sh`, and the operations package integrity check.

### Task 4: End-to-end acceptance and delivery package

**Files:**
- Modify: `scripts/operations_acceptance.py`
- Modify: `backend/tests/test_operations_delivery.py`
- Modify: `docs/operations.md`

- [x] Add a local acceptance mode using temporary backup roots and a fake rclone remote; verify upload/readback/retention without Google credentials or production data.
- [ ] Run the complete targeted operations regression, frontend tests, and TypeScript check.
- [x] Build the committed-source offline package and verify its SHA-256 and file manifest.
- [x] Provide the user a single ECS console setup sequence that requires the user to authorize Google OAuth locally; never request the OAuth token or age private key in chat.
- [x] Keep live Google authorization, quota confirmation, Windows private-key decryption, and remote restore drill pending until the user runs the setup and returns only sanitized status output.

## Self-Review

- The plan covers encryption, OAuth boundaries, quota, upload verification, remote retention, admin status, deployment, and disaster-recovery validation from the approved design.
- No destructive remote cleanup occurs before a verified new object exists; unknown names are never automatically deleted.
- Production restore and financial decisions are excluded from automated acceptance.
- Live Google OAuth, free quota, and private-key recovery require user-controlled setup and are not claimed from local tests.
