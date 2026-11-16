# Operations backup implementation plan

**Goal:** Daily local recovery points, weekly isolated restore, five-minute checks and admin status, deploy on ECS.
**Architecture:** root systemd tasks atomically write a safe public summary; API reads only; PostgreSQL dump with exported snapshot and original source file manifests.
**Spec:** docs/superpowers/specs/2026-11-16-operations-backup-design.md approved.

## Shared contracts

State file /var/lib/finsentinel/operations/status.json: {schema_version:1,checked_at:UTC ISO,status:ok|warning|critical|unknown,checks:[{id,label,status,reason,checked_at,duration_ms}],history:[{at,check_id,status,reason}]}. API GET /api/v1/admin/operations same shape; never expose paths/config/log output/credentials. AUTH_ENABLED must be true and user admin even in test/demo. Missing/corrupt/stale status sanitized, no raw errors.
Backup files /var/backups/finsentinel/backup-UTCSTAMP-UUID/{manifest.json,database.dump,artifacts/,config.tar.gz}; manifest schema_version1,managed_by=finsentinel-operations,created_at,source_revision,table_counts, files map safe relative paths=>{sha256,size},artifact_refs safe metadata. COMPLETE only atomic publication after validation. retention7 complete managed backups.
Task runner CLI python -m scripts.operations_runner {backup|restore|check}, shared --backup-root --state-root defaults as above. Backup/restore last result root-only sidecar files under state-root/private, check task emits safe status.json. Linux units root, backups03:30 Asia/Shanghai daily, restore04:30 Asia/Shanghai Sundays, check5min. Jobs serialize backup+restore, monitor separate lock; state event history max200.

## Task1 backup/recovery
- [ ] Failing tests for safe paths, symlink rejection, retention success-only, manifest integrity and restore forbidden production name.
- [ ] scripts/operations_backup.py plus tests; PG exported snapshot counts and referenced ingestion artifacts + metadata + configured sources, root-only archive; no app stops.
- [ ] Recovery dedicated DB prefix finsentinel_ops_restore_, precreate vector optional in CI, pg_restore no-owner/no-privileges/no-comments; count/schema/reference checks; created DB cleanup bounded.
- [ ] CI PostgreSQL fixture roundtrip test, no production writes; no default source key/cert dumps in CI.

## Task2 checks/backend API
- [ ] Failing status schema/threshold/stale/history/auth/sanitization tests.
- [ ] scripts/operations_runner.py, backend/app/operations.py API route + main wiring; no-shell API and strict allowlist output.
- [ ] Timeout bounded health/units/disk/TLS/backup/restore checks; unknown never green, root status writer atomic; units and local HTTPS checks no public availability claims.

## Task3 frontend
- [ ] /admin/operations page safe role gated authFetch; service/disk/cert/backup/restore/history cards, refresh/errors, existing theme mobile, admin settings link.
- [ ] node parser tests and tsc; independent review.

## Task4 delivery/root integration
- [ ] deploy/ecs/install-operations-offline.sh package integrity/locks/backup/prebuild/cutover/rollback existing auth+TLS, units/trusted readonly smoke.
- [ ] First root backup and dedicated restore before timers; don't grant backend root privilege; status dir0750 root:finsentinel, backup0700.
- [ ] source-only package_operations.py + docs/readme, exact staged paths, backend full tests+frontend35 tests+Linux build+bash-n+PG CI.
- [ ] Independent final source review, verified main push, deterministic tar SHA256 and single ECS console command. No cloud acceptance claim until output/browser verifies.
