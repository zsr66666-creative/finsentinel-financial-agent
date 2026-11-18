#!/usr/bin/env bash
# Local backups and operations upgrade; source-only verified console package.
# Preserves users, sessions, corpus, vectors, HTTPS and previous builds.
set -euo pipefail
umask 022

readonly package_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd /
readonly revision="$(cat "$package_root/SOURCE_REVISION")"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid source revision'; exit 1; }
readonly live='/opt/finsentinel/frontend/.next'
readonly service='finsentinel-frontend'

if [[ $EUID -ne 0 ]]; then
  echo 'Run this deployment script as root.' >&2
  exit 1
fi
for command in flock systemctl python3 sudo npm tar pg_dump nginx sshd ssh-keygen useradd getent passwd chpasswd openssl; do
  command -v "$command" >/dev/null
done
install -d -o root -g root -m 700 /run/lock/finsentinel-deploy
exec 9>/run/lock/finsentinel-deploy/research-desk.lock
flock -n 9 || { echo 'Another frontend deployment is running.' >&2; exit 1; }

# Refuse other service layouts before creating a release or stopping anything.
systemctl show "$service" -p ExecStart --value | grep -Fq "$live/standalone/server.js"
systemctl is-active --quiet "$service"
nginx -t
systemctl is-active --quiet nginx
for name in finsentinel-backend finsentinel-query-encoder finsentinel-ingestion-worker; do systemctl is-active --quiet "$name"; done
[[ -x /opt/finsentinel/.venv/bin/python ]]
available_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
[[ "$available_kib" -ge 716800 ]] || { echo 'Less than 700 MiB available; inspect memory before building'; exit 1; }
[[ -d "$live" && ! -L "$live" ]]
id finsentinel >/dev/null
python3 - <<'PYPREFLIGHT'
from pathlib import Path
for raw in ('/opt/finsentinel-releases','/opt/finsentinel-operations-venv','/var/lib/finsentinel','/var/lib/finsentinel/deploy-reports','/var/lib/finsentinel/operations/private','/var/backups/finsentinel','/etc/finsentinel','/srv/finsentinel-sftp','/etc/ssh/sshd_config','/etc/ssh/authorized_keys'):
    p=Path(raw)
    if any(c.is_symlink() for c in (p,*p.parents)):
        raise SystemExit('Refusing symlink in maintenance path')
PYPREFLIGHT
install -d -o root -g root -m 755 /opt/finsentinel-releases
release="$(mktemp -d /opt/finsentinel-releases/operations-XXXXXXXX)"
chmod 755 "$release"
printf '%s\n' "$revision" >"$release/SOURCE_REVISION"
echo "Staging $revision in $release; the current frontend keeps serving."

python3 - "$package_root" "$release" <<'PYARCHIVE'
import hashlib, json, shutil, sys
from pathlib import Path, PurePosixPath
source, destination = map(Path, sys.argv[1:])
manifest = json.loads((source / 'PACKAGE_FILES.json').read_text())
if not isinstance(manifest, dict) or not manifest:
    raise SystemExit('Missing package manifest')
for name, expected in manifest.items():
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0] not in ('frontend','backend','scripts','deploy','docs'):
        raise SystemExit('Unsafe manifest path')
    path = source.joinpath(*rel.parts)
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f'Package integrity check failed: {name}')
files = {p.relative_to(source).as_posix() for root in ('frontend','backend','scripts') for p in (source / root).rglob('*') if p.is_file()}
if files != {name for name in manifest if name.startswith(('frontend/','backend/','scripts/'))}:
    raise SystemExit('Frontend file list differs from manifest')
for name in files:
    src = source / name
    if any(parent.is_symlink() for parent in src.parents if parent != source.parent):
        raise SystemExit('Symlink in package')
    dst = destination / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
print(f'PASS package manifest; staged {len(files)} source files')
PYARCHIVE

[[ -f "$release/frontend/package-lock.json" ]]
chown -R finsentinel:finsentinel "$release/frontend"
install -d -o finsentinel -g finsentinel -m 750 /var/lib/finsentinel/npm-cache
sudo -u finsentinel env NEXT_PUBLIC_API_URL='' NEXT_TELEMETRY_DISABLED=1 \
  bash -c 'cd "$1" && npm ci --cache /var/lib/finsentinel/npm-cache && npm test && npm run build' \
  _ "$release/frontend"

# Tests use a workspace-local tmp_path fixture; keep source directories root owned.
install -d -o finsentinel -g finsentinel -m 700 "$release/.test-tmp-week13"
sudo -u finsentinel env PYTHONPATH="$release/backend:$release" AUTH_ENABLED=false \
  bash -c 'cd "$1" && /opt/finsentinel/.venv/bin/python -m pytest backend/tests/test_operations.py backend/tests/test_operations_runner.py backend/tests/test_operations_backup.py backend/tests/test_operations_offsite.py -q -p no:cacheprovider' _ "$release"

standalone="$release/frontend/.next/standalone"
[[ -f "$standalone/server.js" && -d "$release/frontend/.next/static" ]]
# Assemble all application-controlled output as the service account.
sudo -u finsentinel bash -s -- "$live" "$release" "$standalone" <<'ASSEMBLE'
set -euo pipefail
live="$1"; release="$2"; standalone="$3"
# Preserve old content-hashed assets for browser tabs open during the deployment.
if [[ -d "$live/static" ]]; then
  python3 - "$live/static" "$release/frontend/.next/static" <<'PY'
import os
from pathlib import Path
import shutil
import sys

old, new = map(Path, sys.argv[1:])
copied = 0
for directory, _, files in os.walk(old, followlinks=False):
    for name in files:
        source = Path(directory) / name
        if source.is_symlink() or not source.is_file():
            continue
        target = new / source.relative_to(old)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied += 1
print(f'Preserved {copied} previous static assets without overwriting new assets')
PY
fi
mkdir -p "$standalone/.next"
cp -a "$release/frontend/.next/static" "$standalone/.next/"
if [[ -d "$release/frontend/public" ]]; then
  cp -a "$release/frontend/public" "$standalone/"
fi
cp "$release/SOURCE_REVISION" "$release/frontend/.next/SOURCE_REVISION"


ASSEMBLE

# Privileged maintenance never imports application-writable Python code/dependencies.
# Frontend build used the service account above; seal all staged source before root execution.
chown -R root:root "$release"
chmod -R go-w "$release"
# Reverify every root-imported file against the authenticated package after the build.
python3 - "$package_root" "$release" <<'PYSEAL'
import hashlib,json,sys
from pathlib import Path,PurePosixPath
package,release=map(Path,sys.argv[1:])
manifest=json.loads((package/'PACKAGE_FILES.json').read_text())
expected={n:h for n,h in manifest.items() if n.startswith(('backend/','scripts/'))}
actual={p.relative_to(release).as_posix() for part in ('backend','scripts') for p in (release/part).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
if actual != set(expected):raise SystemExit('Privileged source file set changed')
for name,digest in expected.items():
    p=release/name
    if p.is_symlink() or any(parent.is_symlink() for parent in p.parents) or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
        raise SystemExit('Privileged source integrity mismatch')
    st=p.stat()
    if st.st_uid!=0 or st.st_mode & 0o022:raise SystemExit('Privileged source permissions unsafe')
# Bytecode generated by unprivileged tests is never a trusted root import source.
import shutil
for part in ('backend','scripts'):
    for p in (release/part).rglob('__pycache__'):
        if p.is_symlink():raise SystemExit('Unsafe bytecode path')
        shutil.rmtree(p)
PYSEAL
ops_python=/opt/finsentinel-operations-venv/bin/python
if [[ ! -x "$ops_python" ]]; then
  python3 -m venv /opt/finsentinel-operations-venv
fi
python3 - /opt/finsentinel-operations-venv <<'PYTRUST'
import os,stat,sys
from pathlib import Path
root=Path(sys.argv[1])
for p in [root,*root.rglob('*')]:
    if p.is_symlink():
        # Standard venv interpreter symlinks may target root-controlled system Python.
        target=p.resolve(strict=True)
        if not (target.is_relative_to(root) or str(target).startswith(('/usr/bin/','/usr/lib/'))):
            raise SystemExit('Unsafe operations environment symlink')
    else:target=p
    s=target.stat()
    if s.st_uid!=0 or s.st_mode & 0o022:
        raise SystemExit('Operations environment must be root owned and nonwritable by group/others')
PYTRUST
"$ops_python" -m pip install --disable-pip-version-check --timeout 30 'SQLAlchemy==2.0.44' 'psycopg[binary]==3.2.12' 'fastapi==0.121.1'
# Backup before applying additive migration or switching service configuration.
install -d -o root -g root -m 700 "$release/backup"
sudo -u postgres pg_dump -Fc -d finsentinel > "$release/backup/database.dump"
chmod 600 "$release/backup/database.dump"
[[ -s "$release/backup/database.dump" ]]
backend_drop='/etc/systemd/system/finsentinel-backend.service.d/99-z-operations.conf'
mkdir -p /etc/systemd/system/finsentinel-backend.service.d
backend_previous=0
if [[ -f "$backend_drop" ]]; then cp -p "$backend_drop" "$release/backup/backend.conf"; backend_previous=1; fi
managed_names=(finsentinel-ops-backup.service finsentinel-ops-backup.timer finsentinel-ops-restore.service finsentinel-ops-restore.timer finsentinel-ops-check.service finsentinel-ops-check.timer)
for name in "${managed_names[@]}"; do
  path="/etc/systemd/system/$name"
  [[ ! -L "$path" ]] || { echo "Refusing symlink unit: $name" >&2; exit 1; }
  if [[ -f "$path" ]]; then cp -p "$path" "$release/backup/$name"; fi
  systemctl is-enabled "$name" > "$release/backup/$name.timer-enabled" 2>/dev/null || true
  systemctl is-active "$name" > "$release/backup/$name.timer-active" 2>/dev/null || true
done
sshd_config='/etc/ssh/sshd_config'
sshd_auth_dir='/etc/ssh/authorized_keys'
sshd_auth_file="$sshd_auth_dir/finsentinel-backup-pull"
export_config='/etc/finsentinel/offsite-export.env'
[[ -f "$sshd_config" && ! -L "$sshd_config" ]] || { echo 'Missing or unsafe sshd configuration.' >&2; exit 1; }
[[ ! -L "$sshd_auth_file" && ! -L "$export_config" ]] || { echo 'Refusing symlink in SFTP configuration.' >&2; exit 1; }
cp -p "$sshd_config" "$release/backup/sshd_config"
sshd_auth_previous=0
if [[ -f "$sshd_auth_file" ]]; then cp -p "$sshd_auth_file" "$release/backup/sftp-authorized-keys"; sshd_auth_previous=1; fi
export_config_previous=0
if [[ -f "$export_config" ]]; then cp -p "$export_config" "$release/backup/offsite-export.env"; export_config_previous=1; fi
[[ -f /root/finsentinel-backup-pull.pub && ! -L /root/finsentinel-backup-pull.pub ]] || { echo 'Place the dedicated Windows SSH public key at /root/finsentinel-backup-pull.pub.' >&2; exit 1; }
mapfile -t sftp_key_lines < /root/finsentinel-backup-pull.pub
[[ "${#sftp_key_lines[@]}" -eq 1 && "${sftp_key_lines[0]}" =~ ^ssh-ed25519[[:space:]]+[^[:space:]]+([[:space:]].*)?$ ]] || { echo 'Expected exactly one ssh-ed25519 public key.' >&2; exit 1; }
ssh-keygen -lf /root/finsentinel-backup-pull.pub >/dev/null
units_started=0
switch_started=0
ssh_started=0
sftp_user_created=0
frontend_stopped=0
frontend_moved=0
rollback_on_exit() {
  status=$?
  trap - EXIT INT TERM
  if [[ "$switch_started" -eq 1 || "$ssh_started" -eq 1 ]]; then
    set +e
    rollback_failed=0
    echo "Deployment failed; restoring previous frontend/backend configuration: $release" >&2
    if [[ "$switch_started" -eq 1 && "$frontend_stopped" -eq 1 ]]; then
      systemctl stop "$service" || rollback_failed=1
      if [[ "$frontend_moved" -eq 1 ]]; then
        if [[ -e "$live" ]]; then mv "$live" "$release/failed-next" || rollback_failed=1; fi
        mv "$release/previous-next" "$live" || rollback_failed=1
      fi
      systemctl start "$service" || rollback_failed=1
    fi
    if [[ "$switch_started" -eq 1 && "$units_started" -eq 1 ]]; then
      for name in "${managed_names[@]}"; do
        systemctl stop "$name" || true
        if [[ -f "$release/backup/$name" ]]; then cp -p "$release/backup/$name" "/etc/systemd/system/$name" || rollback_failed=1; else rm -f -- "/etc/systemd/system/$name" || rollback_failed=1; fi
      done
      systemctl daemon-reload || rollback_failed=1
      for name in "${managed_names[@]}"; do
        if [[ "$name" == *.timer ]]; then
          if grep -qx enabled "$release/backup/$name.timer-enabled"; then systemctl enable "$name" || rollback_failed=1; else systemctl disable "$name" 2>/dev/null || true; fi
          if grep -qx active "$release/backup/$name.timer-active"; then systemctl start "$name" || rollback_failed=1; fi
        fi
      done
    fi
    if [[ "$switch_started" -eq 1 ]]; then
      if [[ "$backend_previous" -eq 1 ]]; then cp -p "$release/backup/backend.conf" "$backend_drop" || rollback_failed=1; else rm -f "$backend_drop" || rollback_failed=1; fi
      systemctl daemon-reload || rollback_failed=1
      systemctl restart finsentinel-backend || rollback_failed=1
    fi
    if [[ "$ssh_started" -eq 1 ]]; then
      cp -p "$release/backup/sshd_config" "$sshd_config" || rollback_failed=1
      if [[ "$sshd_auth_previous" -eq 1 ]]; then cp -p "$release/backup/sftp-authorized-keys" "$sshd_auth_file" || rollback_failed=1; else rm -f "$sshd_auth_file" || rollback_failed=1; fi
      if [[ "$export_config_previous" -eq 1 ]]; then cp -p "$release/backup/offsite-export.env" "$export_config" || rollback_failed=1; else rm -f "$export_config" || rollback_failed=1; fi
      if [[ "$sftp_user_created" -eq 1 ]]; then userdel finsentinel-backup-pull || rollback_failed=1; fi
      sshd -t || rollback_failed=1
      systemctl reload ssh || rollback_failed=1
    fi
    if [[ "$rollback_failed" -ne 0 ]]; then echo 'ROLLBACK ERROR: inspect services and retained backup immediately.' >&2; fi
    echo 'Backups and diagnostic results retained; no production human reviews or account changes made.' >&2
    [[ "$status" -ne 0 ]] || status=1
  fi
  exit "$status"
}
trap rollback_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
run_admin() {
  sudo -u finsentinel env PYTHONPATH="$release/backend:$release" \
    DATABASE_URL='postgresql+psycopg:///finsentinel?host=/var/run/postgresql' \
    /opt/finsentinel/.venv/bin/python "$@"
}
run_admin -m scripts.manage_accounts check
report_root="/var/lib/finsentinel/deploy-reports/$(basename "$release")"
# Dedicated app-writable diagnostics is outside every root Python import path.
# Root task paths must not be replaceable by the application account.
python3 - <<'PYPARENTS'
import os,stat
from pathlib import Path
for raw in ('/var/lib/finsentinel','/var/backups/finsentinel','/var/lib/finsentinel/operations/private','/var/lib/finsentinel/deploy-reports'):
    p=Path(raw)
    if any(c.is_symlink() for c in (p,*p.parents)):
        raise SystemExit('Refusing symlink in maintenance data path')
p=Path('/var/lib/finsentinel')
if p.exists():
    s=p.stat()
    print('Maintenance parent verified; locking directory ownership (child ownership preserved)')
PYPARENTS
install -d -o root -g root -m 755 /var/lib/finsentinel
install -d -o root -g root -m 755 /var/lib/finsentinel/deploy-reports
install -d -o finsentinel -g finsentinel -m 750 "$report_root"
install -d -o root -g root -m 700 /var/backups/finsentinel
install -d -o root -g finsentinel -m 750 /var/lib/finsentinel/operations
install -d -o root -g root -m 700 /var/lib/finsentinel/operations/private
install -d -o root -g root -m 750 /etc/finsentinel
export_root='/srv/finsentinel-sftp/finsentinel-backup-pull/exports'
command -v age >/dev/null || { echo 'age is required for encrypted recovery exports.' >&2; exit 1; }
ssh_started=1
install -d -o root -g root -m 755 /etc/ssh/authorized_keys
install -d -o root -g root -m 755 /srv/finsentinel-sftp
install -d -o root -g root -m 755 /srv/finsentinel-sftp/finsentinel-backup-pull
install -d -o root -g root -m 755 "$export_root"
printf '%s\n' "${sftp_key_lines[0]}" > "$sshd_auth_file"
chown root:root "$sshd_auth_file"
chmod 644 "$sshd_auth_file"
if ! getent passwd finsentinel-backup-pull >/dev/null; then
  useradd --system --no-create-home --home-dir / --shell /usr/sbin/nologin finsentinel-backup-pull
  sftp_user_created=1
  random_password="$(openssl rand -base64 48)"
  password_hash="$(printf '%s' "$random_password" | openssl passwd -6 -stdin)"
  unset random_password
  printf 'finsentinel-backup-pull:%s\n' "$password_hash" | chpasswd --encrypted
  unset password_hash
else
  [[ "$(getent passwd finsentinel-backup-pull | cut -d: -f7)" == /usr/sbin/nologin ]] || { echo 'Existing SFTP account has an unexpected shell.' >&2; exit 1; }
fi
if [[ ! -e "$export_config" ]]; then
  printf 'FINSENTINEL_AGE_RECIPIENT=\nFINSENTINEL_EXPORT_ROOT=%s\n' "$export_root" > "$export_config"
fi
chown root:root "$export_config"
chmod 600 "$export_config"
python3 - "$export_config" "$export_root" <<'PYEXPORTCONFIG'
import re,sys
from pathlib import Path
path=Path(sys.argv[1]); expected_root=sys.argv[2]
rows=path.read_text(encoding='ascii').splitlines()
values={}
for row in rows:
    if not row or row.startswith('#'): continue
    key,sep,value=row.partition('=')
    if not sep or key not in ('FINSENTINEL_AGE_RECIPIENT','FINSENTINEL_EXPORT_ROOT') or key in values:
        raise SystemExit('Invalid export configuration format')
    values[key]=value
if set(values)!={'FINSENTINEL_AGE_RECIPIENT','FINSENTINEL_EXPORT_ROOT'}:
    raise SystemExit('Incomplete export configuration')
if values['FINSENTINEL_AGE_RECIPIENT'] and not re.fullmatch(r'age1[0-9a-z]{8,100}',values['FINSENTINEL_AGE_RECIPIENT']):
    raise SystemExit('Invalid age recipient')
if values['FINSENTINEL_EXPORT_ROOT']!=expected_root:
    raise SystemExit('Unexpected export directory')
PYEXPORTCONFIG
root_auth_before="$(sshd -T -C user=root,host=localhost,addr=127.0.0.1 | awk '$1 ~ /^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|authorizedkeysfile|authenticationmethods)$/')"
python3 - "$sshd_config" <<'PYSSHD'
import os,sys,tempfile
from pathlib import Path
path=Path(sys.argv[1])
start='# BEGIN FINSENTINEL SFTP ACCOUNT'
end='# END FINSENTINEL SFTP ACCOUNT'
text=path.read_text(encoding='utf-8')
if text.count(start)!=text.count(end) or text.count(start)>1:
    raise SystemExit('Invalid managed SSH block markers')
if start in text:
    before,rest=text.split(start,1)
    _,after=rest.split(end,1)
    text=before.rstrip()+'\n'+after.lstrip('\n')
block='''# BEGIN FINSENTINEL SFTP ACCOUNT
Match all
Match User finsentinel-backup-pull
    AuthorizedKeysFile /etc/ssh/authorized_keys/%u
    AuthenticationMethods publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    ChrootDirectory /srv/finsentinel-sftp/finsentinel-backup-pull
    ForceCommand internal-sftp -R -d /exports
    DisableForwarding yes
    AllowTcpForwarding no
    AllowAgentForwarding no
    PermitTTY no
    X11Forwarding no
# END FINSENTINEL SFTP ACCOUNT
'''
fd,name=tempfile.mkstemp(prefix='.sshd_config-',dir=str(path.parent))
with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as stream:
    stream.write(text.rstrip()+'\n\n'+block)
    stream.flush();os.fsync(stream.fileno())
os.chmod(name,path.stat().st_mode & 0o777)
os.replace(name,path)
PYSSHD
sshd -t
sftp_effective="$(sshd -T -C user=finsentinel-backup-pull,host=localhost,addr=127.0.0.1)"
grep -Fxq 'authorizedkeysfile /etc/ssh/authorized_keys/%u' <<< "$sftp_effective"
grep -Fxq 'authenticationmethods publickey' <<< "$sftp_effective"
grep -Fxq 'passwordauthentication no' <<< "$sftp_effective"
grep -Fxq 'chrootdirectory /srv/finsentinel-sftp/finsentinel-backup-pull' <<< "$sftp_effective"
grep -Fxq 'forcecommand internal-sftp -R -d /exports' <<< "$sftp_effective"
grep -Fxq 'disableforwarding yes' <<< "$sftp_effective"
grep -Fxq 'permittty no' <<< "$sftp_effective"
root_auth_after="$(sshd -T -C user=root,host=localhost,addr=127.0.0.1 | awk '$1 ~ /^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|authorizedkeysfile|authenticationmethods)$/')"
[[ "$root_auth_before" == "$root_auth_after" ]] || { echo 'Root SSH effective settings changed; rolling back.' >&2; exit 1; }
systemctl reload ssh
run_ops() {
  (cd "$release" && env PYTHONPATH="$release/backend:$release" \
    DATABASE_URL='postgresql+psycopg:///finsentinel?host=/var/run/postgresql' \
    OPERATIONS_SOURCE_REVISION="$revision" \
    /opt/finsentinel-operations-venv/bin/python -m scripts.operations_runner "$@")
}
# Complete the first real recovery point and isolated restore before enabling timers.
run_ops backup
run_ops restore
switch_started=1
cat > "$backend_drop" <<EOF
[Service]
Environment="AUTH_ENABLED=true"
Environment="AUTH_ORIGIN=https://120.24.108.60"
Environment="AUTH_COOKIE_SECURE=true"
Environment="OPERATIONS_STATUS_FILE=/var/lib/finsentinel/operations/status.json"
ExecStart=
ExecStart=/opt/finsentinel/.venv/bin/python -m uvicorn app.main:app --app-dir $release/backend --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
EOF
systemctl daemon-reload
systemctl restart finsentinel-backend
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health
run_admin -m scripts.accounts_acceptance --backend-only --output "$report_root/api-acceptance.json"
frontend_stopped=1
systemctl stop "$service"
mv "$live" "$release/previous-next"
frontend_moved=1
cp -a "$release/frontend/.next" "$live"
chown -R finsentinel:finsentinel "$live"
systemctl start "$service"

# Trusted TLS acceptance also checks app shells and every referenced CSS/JS asset.
run_admin -m scripts.operations_acceptance --output "$report_root/https-acceptance.json"
# Only root task units can write backup/state; application API is read-only.
units_started=1
for job in backup restore check; do
  cat > "/etc/systemd/system/finsentinel-ops-$job.service" <<EOF
[Unit]
Description=FinSentinel operations $job
Wants=network-online.target
After=network-online.target postgresql.service

[Service]
Type=oneshot
User=root
Group=root
UMask=0077
WorkingDirectory=$release
Environment="PYTHONPATH=$release/backend:$release"
Environment="DATABASE_URL=postgresql+psycopg:///finsentinel?host=/var/run/postgresql"
Environment="OPERATIONS_SOURCE_REVISION=$revision"
EnvironmentFile=-/etc/finsentinel/offsite-export.env
ExecStart=/opt/finsentinel-operations-venv/bin/python -m scripts.operations_runner $job
TimeoutStartSec=30min
Nice=10
EOF
  if [[ "$job" == check ]]; then
    sed -i 's/TimeoutStartSec=30min/TimeoutStartSec=2min/' "/etc/systemd/system/finsentinel-ops-$job.service"
  fi
done
cat > /etc/systemd/system/finsentinel-ops-backup.timer <<'EOF'
[Unit]
Description=Daily FinSentinel local backup
[Timer]
OnCalendar=*-*-* 03:30:00 Asia/Shanghai
RandomizedDelaySec=5min
Persistent=true
[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/finsentinel-ops-restore.timer <<'EOF'
[Unit]
Description=Weekly FinSentinel isolated restore verification
[Timer]
OnCalendar=Sun *-*-* 04:30:00 Asia/Shanghai
RandomizedDelaySec=5min
Persistent=true
[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/finsentinel-ops-check.timer <<'EOF'
[Unit]
Description=FinSentinel health checks every five minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=10s
[Install]
WantedBy=timers.target
EOF
systemd-analyze verify /etc/systemd/system/finsentinel-ops-{backup,restore,check}.{service,timer}
systemctl daemon-reload
systemctl enable --now finsentinel-ops-backup.timer finsentinel-ops-restore.timer finsentinel-ops-check.timer
# Let systemd coalesce an immediate OnBootSec trigger with this initial check.
systemctl start finsentinel-ops-check.service
# Only a schema and permission check, no operational secrets printed.
run_admin -c 'from app.operations import LABELS, read_status; s=read_status(); assert len(s["checks"]) == len(LABELS) == 18, "Invalid operations status"; print("PASS status reader; aggregate=" + s["status"])'
for name in nginx finsentinel-backend finsentinel-frontend finsentinel-ingestion-worker finsentinel-query-encoder; do
  systemctl is-active --quiet "$name" || { echo "Service not active: $name" >&2; exit 1; }
done
systemctl is-active --quiet finsentinel-ip-cert-renew.timer
nginx -t
switch_started=0
trap - EXIT INT TERM
printf 'PASS operations deployment; SOURCE_REVISION=%s\nRetained release and backup: %s\n' "$revision" "$release"
echo 'Next: set FINSENTINEL_AGE_RECIPIENT in /etc/finsentinel/offsite-export.env, then configure the Windows pull task and ECS SSH ingress /32.'
