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
for command in flock systemctl python3 sudo npm tar pg_dump nginx; do
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
for raw in ('/opt/finsentinel-releases','/opt/finsentinel-operations-venv','/var/lib/finsentinel','/var/lib/finsentinel/deploy-reports','/var/lib/finsentinel/operations/private','/var/backups/finsentinel'):
    p=Path(raw)
    if any(c.is_symlink() for c in (p,*p.parents)):
        raise SystemExit('Refusing symlink in maintenance path')
PYPREFLIGHT
install -d -o root -g root -m 755 /opt/finsentinel-releases
release="$(mktemp -d /opt/finsentinel-releases/research-library-XXXXXXXX)"
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
  bash -c 'cd "$1" && /opt/finsentinel/.venv/bin/python -m pytest backend/tests/test_personal_research.py backend/tests/test_personal_research_api.py -q -p no:cacheprovider' _ "$release"

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
# Backup before applying additive migration or switching service configuration.
install -d -o root -g root -m 700 "$release/backup"
sudo -u postgres pg_dump -Fc -d finsentinel > "$release/backup/database.dump"
chmod 600 "$release/backup/database.dump"
[[ -s "$release/backup/database.dump" ]]
backend_drop='/etc/systemd/system/finsentinel-backend.service.d/99-zz-research-library.conf'
[[ ! -L "$backend_drop" ]]
mkdir -p /etc/systemd/system/finsentinel-backend.service.d
backend_previous=0
if [[ -f "$backend_drop" ]]; then cp -p "$backend_drop" "$release/backup/backend.conf"; backend_previous=1; fi
switch_started=0
frontend_stopped=0
frontend_moved=0
rollback_on_exit() {
  status=$?
  trap - EXIT INT TERM
  if [[ "$switch_started" -eq 1 ]]; then
    set +e
    rollback_failed=0
    echo "Deployment failed; restoring previous frontend/backend configuration: $release" >&2
    if [[ "$frontend_stopped" -eq 1 ]]; then
      systemctl stop "$service" || rollback_failed=1
      if [[ "$frontend_moved" -eq 1 ]]; then
        if [[ -e "$live" ]]; then mv "$live" "$release/failed-next" || rollback_failed=1; fi
        mv "$release/previous-next" "$live" || rollback_failed=1
      fi
      systemctl start "$service" || rollback_failed=1
    fi
    if [[ "$backend_previous" -eq 1 ]]; then cp -p "$release/backup/backend.conf" "$backend_drop" || rollback_failed=1; else rm -f "$backend_drop" || rollback_failed=1; fi
    systemctl daemon-reload || rollback_failed=1
    systemctl restart finsentinel-backend || rollback_failed=1
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
# Validate a complete recovery point using the existing trusted root units.
systemctl start finsentinel-ops-backup.service
systemctl start finsentinel-ops-restore.service
run_admin -m scripts.manage_research_library migrate
run_admin -m scripts.manage_research_library check
report_root="/var/lib/finsentinel/deploy-reports/$(basename "$release")"
[[ -d /var/lib/finsentinel/deploy-reports && ! -L /var/lib/finsentinel/deploy-reports ]]
[[ ! -e "$report_root" && ! -L "$report_root" ]]
install -d -o finsentinel -g finsentinel -m 750 "$report_root"
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
run_admin -m scripts.research_library_acceptance --output "$report_root/https-acceptance.json"
# Preserve existing operations units and refresh their status.
systemctl start finsentinel-ops-check.service
run_admin -c 'from app.operations import read_status; s=read_status(); assert len(s["checks"]) == 18 and s["status"] in ("ok","warning"), "Operations checks need attention"; print("PASS preserved operations; aggregate=" + s["status"])' 
for name in nginx finsentinel-backend finsentinel-frontend finsentinel-ingestion-worker finsentinel-query-encoder; do
  systemctl is-active --quiet "$name" || { echo "Service not active: $name" >&2; exit 1; }
done
for timer in finsentinel-ip-cert-renew.timer finsentinel-ops-backup.timer finsentinel-ops-restore.timer finsentinel-ops-check.timer; do systemctl is-active --quiet "$timer"; done
nginx -t
switch_started=0
trap - EXIT INT TERM
printf 'PASS research library deployment; SOURCE_REVISION=%s\nRetained release and backup: %s\n' "$revision" "$release"
echo 'Next: open https://120.24.108.60/my-research and verify private favorites and history.'
