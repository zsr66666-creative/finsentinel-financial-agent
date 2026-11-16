#!/usr/bin/env bash
# Real accounts upgrade. Run from a verified source-only package in the root console.
# Adds user/session tables; preserves corpus, vectors, HTTPS and previous builds.
set -euo pipefail
umask 022

readonly package_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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
site=/etc/nginx/sites-available/finsentinel
[[ -f "$site" && ! -L "$site" ]]
[[ "$(readlink -f /etc/nginx/sites-enabled/finsentinel)" == "$site" ]]
for name in finsentinel-backend finsentinel-query-encoder finsentinel-ingestion-worker; do systemctl is-active --quiet "$name"; done
[[ -x /opt/finsentinel/.venv/bin/python ]]
available_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
[[ "$available_kib" -ge 716800 ]] || { echo 'Less than 700 MiB available; inspect memory before building'; exit 1; }
[[ -d "$live" && ! -L "$live" ]]
id finsentinel >/dev/null
install -d -o root -g root -m 755 /opt/finsentinel-releases
release="$(mktemp -d /opt/finsentinel-releases/accounts-XXXXXXXX)"
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
chown -R finsentinel:finsentinel "$release"
install -d -o finsentinel -g finsentinel -m 750 /var/lib/finsentinel/npm-cache
sudo -u finsentinel env NEXT_PUBLIC_API_URL='' NEXT_TELEMETRY_DISABLED=1 \
  bash -c 'cd "$1" && npm ci --cache /var/lib/finsentinel/npm-cache && npm test && npm run build' \
  _ "$release/frontend"

# A new dependency only; no upgrades of existing application packages.
/opt/finsentinel/.venv/bin/python -m pip install --disable-pip-version-check --timeout 30 'Pillow==12.0.0'
sudo -u finsentinel env PYTHONPATH="$release/backend:$release" AUTH_ENABLED=false \
  bash -c 'cd "$1" && /opt/finsentinel/.venv/bin/python -m pytest backend/tests/test_accounts.py backend/tests/test_accounts_api.py -q -p no:cacheprovider' _ "$release"

standalone="$release/frontend/.next/standalone"
[[ -f "$standalone/server.js" && -d "$release/frontend/.next/static" ]]
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
chown -R finsentinel:finsentinel "$release"

# Backup before applying additive migration or switching service configuration.
install -d -o root -g root -m 700 "$release/backup"
sudo -u postgres pg_dump -Fc -d finsentinel > "$release/backup/database.dump"
chmod 600 "$release/backup/database.dump"
[[ -s "$release/backup/database.dump" ]]
cp -a "$site" "$release/backup/nginx.conf"
run_renderer() {
  PYTHONPATH="$release/backend:$release" /opt/finsentinel/.venv/bin/python -m scripts.account_https_redirect \
    --source "$site" --output "$release/redirect.conf"
}
run_renderer
backend_drop='/etc/systemd/system/finsentinel-backend.service.d/99-real-accounts.conf'
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
    cp -a "$release/backup/nginx.conf" "$site" || rollback_failed=1
    nginx -t && systemctl reload nginx || rollback_failed=1
    if [[ "$rollback_failed" -ne 0 ]]; then echo 'ROLLBACK ERROR: inspect services and retained backup immediately.' >&2; fi
    echo 'Additive account tables and accounts retained; no production human reviews were created.' >&2
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
run_admin -m scripts.manage_accounts migrate
run_admin -m scripts.accounts_pg_acceptance --output "$release/postgres-acceptance.json"
# Interactive secrets are read from the console, never arguments or package files.
[[ -t 0 ]] || { echo 'Run from an interactive Alibaba console for first administrator setup.' >&2; exit 1; }
run_admin -m scripts.manage_accounts bootstrap
run_admin -m scripts.manage_accounts check
switch_started=1
install -m 644 "$release/redirect.conf" "$site"
nginx -t
systemctl reload nginx
cat > "$backend_drop" <<EOF
[Service]
Environment="AUTH_ENABLED=true"
Environment="AUTH_ORIGIN=https://120.24.108.60"
Environment="AUTH_COOKIE_SECURE=true"
ExecStart=
ExecStart=/opt/finsentinel/.venv/bin/python -m uvicorn app.main:app --app-dir $release/backend --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
EOF
systemctl daemon-reload
systemctl restart finsentinel-backend
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health
run_admin -m scripts.accounts_acceptance --backend-only --output "$release/api-acceptance.json"
frontend_stopped=1
systemctl stop "$service"
mv "$live" "$release/previous-next"
frontend_moved=1
cp -a "$release/frontend/.next" "$live"
systemctl start "$service"

# Trusted TLS acceptance also checks app shells and every referenced CSS/JS asset.
run_admin -m scripts.accounts_acceptance --output "$release/https-acceptance.json"
# Ensure the retained HTTP-01 exception still supports short-lived renewal.
/opt/finsentinel-certbot/bin/certbot renew --cert-name finsentinel-ip --dry-run --run-deploy-hooks --no-random-sleep-on-renew
for name in nginx finsentinel-backend finsentinel-frontend finsentinel-ingestion-worker finsentinel-query-encoder; do
  systemctl is-active --quiet "$name" || { echo "Service not active: $name" >&2; exit 1; }
done
systemctl is-active --quiet finsentinel-ip-cert-renew.timer
nginx -t
switch_started=0
trap - EXIT INT TERM
printf 'PASS accounts deployment; SOURCE_REVISION=%s\nRetained release and backup: %s\n' "$revision" "$release"
echo 'Next: open https://120.24.108.60/login and use your administrator account; never send the password to chat.'
