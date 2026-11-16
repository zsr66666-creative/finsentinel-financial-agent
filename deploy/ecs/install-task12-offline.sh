#!/usr/bin/env bash
# Task12 financial review deployment. Run from the verified source-only package as root.
# Adds review table; preserves corpus, vectors, Nginx and previous builds.
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
for name in finsentinel-backend finsentinel-query-encoder finsentinel-ingestion-worker; do systemctl is-active --quiet "$name"; done
[[ -x /opt/finsentinel/.venv/bin/python ]]
available_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
[[ "$available_kib" -ge 716800 ]] || { echo 'Less than 700 MiB available; inspect memory before building'; exit 1; }
[[ -d "$live" && ! -L "$live" ]]
id finsentinel >/dev/null
install -d -o root -g root -m 755 /opt/finsentinel-releases
release="$(mktemp -d /opt/finsentinel-releases/task12-review-XXXXXXXX)"
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

sudo -u finsentinel env PYTHONPATH="$release/backend:$release" \
  bash -c 'cd "$1" && /opt/finsentinel/.venv/bin/python -m pytest backend/tests/test_task12_reviews.py backend/tests/test_task11_financials.py backend/tests/test_persisted_comparison.py -q -p no:cacheprovider' _ "$release"

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
backend_drop='/etc/systemd/system/finsentinel-backend.service.d/95-task12-review.conf'
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
    echo 'Additive review table and committed records retained; acceptance makes no production human decisions.' >&2
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
run_admin -m scripts.task12_acceptance --migrate --database-only --output "$release/database-acceptance.json"
install -d -o root -g finsentinel -m 750 /etc/finsentinel
python3 - <<'PYTOKEN'
import os, re, secrets
from pathlib import Path
p=Path('/etc/finsentinel/financial-review.env')
if p.is_symlink(): raise SystemExit('Refusing symlink credential file')
if p.exists():
    if not re.fullmatch(r'FINANCIAL_REVIEW_TOKEN=[a-f0-9]{64}\n?',p.read_text()):
        raise SystemExit('Existing review credential file format unexpected; inspect locally')
else:
    descriptor=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as stream:stream.write('FINANCIAL_REVIEW_TOKEN='+secrets.token_hex(32)+'\n')
PYTOKEN
chown root:finsentinel /etc/finsentinel/financial-review.env
chmod 640 /etc/finsentinel/financial-review.env
switch_started=1
cat > "$backend_drop" <<EOF
[Service]
EnvironmentFile=/etc/finsentinel/financial-review.env
ExecStart=
ExecStart=/opt/finsentinel/.venv/bin/python -m uvicorn app.main:app --app-dir $release/backend --host 127.0.0.1 --port 8000
EOF
systemctl daemon-reload
systemctl restart finsentinel-backend
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health
run_admin -m scripts.task12_acceptance --output "$release/api-acceptance.json"
frontend_stopped=1
systemctl stop "$service"
mv "$live" "$release/previous-next"
frontend_moved=1
cp -a "$release/frontend/.next" "$live"
systemctl start "$service"

# Check direct Next.js readiness, then Nginx routing and every CSS/JS reference.
python3 - <<'PY'
from html.parser import HTMLParser
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, ProxyHandler, build_opener

opener = build_opener(ProxyHandler({}))

def fetch(base, path, host=None):
    headers = {'Host': host} if host else {}
    with opener.open(Request(base + path, headers=headers), timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f'{path}: HTTP {response.status}')
        return response.read()

for attempt in range(25):
    try:
        html = fetch('http://127.0.0.1:3000', '/compare').decode('utf-8')
        if 'FinSentinel' not in html:
            raise RuntimeError('Direct /compare did not return the reviewed UI')
        break
    except Exception:
        if attempt == 24:
            raise
        time.sleep(2)
print('PASS localhost:3000/compare application shell; interactive login still requires browser acceptance')

class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        value = attrs.get('src') if tag == 'script' else attrs.get('href') if tag == 'link' else None
        if not value:
            return
        url = urlsplit(urljoin('http://120.24.108.60/', value))
        if tag != 'script' and not (url.path.endswith(('.css', '.js'))
                                    or 'stylesheet' in attrs.get('rel', '').split()):
            return
        if url.netloc != '120.24.108.60' or url.scheme != 'http':
            raise RuntimeError(f'Unexpected external CSS/JS reference: {value}')
        self.paths.add(url.path + ('?' + url.query if url.query else ''))

paths = ['/', '/companies', '/reports', '/evidence', '/compare', '/login', '/settings', '/companies/002475', '/companies/002555', '/companies/002230', '/workbench', '/workbench/alerts', '/workbench/companies', '/workbench/review', '/workbench/evals', '/workbench/data']
for path in paths:
    expected = 'FinSentinel'
    html = fetch('http://127.0.0.1', path, '120.24.108.60').decode('utf-8')
    if expected not in html:
        raise RuntimeError(f'{path}: expected page content missing')
    assets = Assets()
    assets.feed(html)
    if not assets.paths:
        raise RuntimeError(f'{path}: no CSS/JS references found')
    for asset in sorted(assets.paths):
        if not fetch('http://127.0.0.1', asset, '120.24.108.60'):
            raise RuntimeError(f'Empty CSS/JS response: {asset}')
    print(f'PASS Nginx Host 120.24.108.60 {path}: HTTP 200; {len(assets.paths)} CSS/JS references HTTP 200')
PY

python3 - <<'PYENCODER'
import json
from urllib.request import ProxyHandler, build_opener
with build_opener(ProxyHandler({})).open('http://127.0.0.1:8081/health',timeout=10) as response:
    assert response.status==200
    json.load(response)
print('PASS existing encoder HTTP health')
PYENCODER
run_admin -m scripts.task12_acceptance --api-url http://127.0.0.1 --host-header 120.24.108.60 --output "$release/nginx-acceptance.json"
for name in nginx finsentinel-backend finsentinel-frontend finsentinel-ingestion-worker finsentinel-query-encoder; do systemctl is-active --quiet "$name" || { echo "Service not active: $name" >&2; exit 1; }; done
switch_started=0
trap - EXIT INT TERM
echo 'Review credential: /etc/finsentinel/financial-review.env; never send it to chat.'
printf 'PASS deployment; SOURCE_REVISION=%s\nRetained release and backup: %s\n' "$revision" "$release"
