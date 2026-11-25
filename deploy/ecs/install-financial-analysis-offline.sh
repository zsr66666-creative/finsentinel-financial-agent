#!/usr/bin/env bash
# Deploy the approved 000157 financial inputs and application code to an existing FinSentinel ECS.
set -euo pipefail
umask 022

readonly package_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly revision="$(cat "$package_root/SOURCE_REVISION")"
readonly live='/opt/finsentinel/frontend/.next'
readonly service='finsentinel-frontend'

[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 1; }
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid source revision.' >&2; exit 1; }
for command in flock systemctl python3 sudo npm tar pg_dump nginx curl; do command -v "$command" >/dev/null; done
install -d -o root -g root -m 700 /run/lock/finsentinel-deploy
exec 9>/run/lock/finsentinel-deploy/financial-analysis.lock
flock -n 9 || { echo 'Another deployment is running.' >&2; exit 1; }

# Match the known ECS layout and reserve enough space for a source build and database backup.
systemctl show "$service" -p ExecStart --value | grep -Fq "$live/standalone/server.js"
systemctl show finsentinel-backend -p ExecStart --value | grep -Fq '/opt/finsentinel/.venv/bin/python'
nginx -t
for name in nginx finsentinel-backend finsentinel-frontend finsentinel-ingestion-worker finsentinel-query-encoder; do
  systemctl is-active --quiet "$name" || { echo "Required service inactive: $name" >&2; exit 1; }
done
[[ -x /opt/finsentinel/.venv/bin/python && -d "$live" && ! -L "$live" ]]
id finsentinel >/dev/null
available_kib="$(df -Pk / | awk 'NR==2 {print $4}')"
database_mib="$(sudo -u postgres psql -d finsentinel -Atc "SELECT ceil(pg_database_size('finsentinel') / 1048576.0)::bigint")"
required_kib="$((3145728 + database_mib * 1024))"
[[ "$available_kib" -ge "$required_kib" ]] || {
  echo "Insufficient disk: need 3 GiB build/switch margin plus up to ${database_mib} MiB database backup." >&2
  df -h /
  exit 1
}
available_mem="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
[[ "$available_mem" -ge 716800 ]] || { echo 'Less than 700 MiB available memory.' >&2; exit 1; }

release="$(mktemp -d /opt/finsentinel-releases/financial-analysis-XXXXXXXX)"
chmod 755 "$release"
printf '%s\n' "$revision" >"$release/SOURCE_REVISION"
python3 - "$package_root" "$release" <<'PY'
import hashlib, json, shutil, sys
from pathlib import Path, PurePosixPath
source, destination = map(Path, sys.argv[1:])
manifest = json.loads((source / 'PACKAGE_FILES.json').read_text())
if not isinstance(manifest, dict) or not manifest:
    raise SystemExit('Missing package manifest')
for name, expected in manifest.items():
    rel = PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0] not in ('frontend','backend','scripts','deploy','data','docs','README.md'):
        raise SystemExit('Unsafe package path')
    path = source.joinpath(*rel.parts)
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f'Package integrity failure: {name}')
    target = destination.joinpath(*rel.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
print(f'PASS package manifest: {len(manifest)} files')
PY

[[ -f "$release/data/verified-financials/000157-2023-2024.jsonl" ]]
chown -R finsentinel:finsentinel "$release"
install -d -o finsentinel -g finsentinel -m 750 /var/lib/finsentinel/npm-cache
sudo -u finsentinel env NEXT_PUBLIC_API_URL='' NEXT_TELEMETRY_DISABLED=1 \
  bash -c 'cd "$1" && npm ci --cache /var/lib/finsentinel/npm-cache && npm test && npx tsc --noEmit && npm run build' _ "$release/frontend"
sudo -u finsentinel env PYTHONPATH="$release/backend:$release" \
  bash -c 'cd "$1" && /opt/finsentinel/.venv/bin/python -m pytest backend/tests/test_verified_financial_import.py backend/tests/test_financial_analysis_api.py backend/tests/test_financial_analysis_contract.py -q -p no:cacheprovider' _ "$release"
available_kib="$(df -Pk / | awk 'NR==2 {print $4}')"
[[ "$available_kib" -ge "$((database_mib * 1024 + 524288))" ]] || {
  echo 'Insufficient space remains for database backup and frontend switch; aborting before backup.' >&2
  df -h /
  exit 1
}
sudo -u finsentinel env PYTHONPATH="$release/backend:$release" \
  DATABASE_URL='postgresql+psycopg:///finsentinel?host=/var/run/postgresql' \
  /opt/finsentinel/.venv/bin/python -m scripts.import_verified_financials \
  --database-url 'postgresql+psycopg:///finsentinel?host=/var/run/postgresql' \
  --corpus "$release/data/verified-financials/000157-2023-2024.jsonl" \
  --artifact-root /var/lib/finsentinel/ingestion --check-only

standalone="$release/frontend/.next/standalone"
[[ -f "$standalone/server.js" && -d "$release/frontend/.next/static" ]]
if [[ -d "$live/static" ]]; then
  python3 - "$live/static" "$release/frontend/.next/static" <<'PY'
import os, shutil, sys
from pathlib import Path
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
print(f'Preserved {copied} existing static assets')
PY
fi
mkdir -p "$standalone/.next"
cp -a "$release/frontend/.next/static" "$standalone/.next/"
[[ ! -d "$release/frontend/public" ]] || cp -a "$release/frontend/public" "$standalone/"
cp "$release/SOURCE_REVISION" "$release/frontend/.next/SOURCE_REVISION"
chown -R finsentinel:finsentinel "$release"

install -d -o root -g root -m 700 "$release/backup"
sudo -u postgres pg_dump -Fc -d finsentinel >"$release/backup/database.dump"
chmod 600 "$release/backup/database.dump"
[[ -s "$release/backup/database.dump" ]]
backend_drop='/etc/systemd/system/finsentinel-backend.service.d/99-financial-analysis.conf'
mkdir -p "$(dirname "$backend_drop")"
backend_previous=0
if [[ -f "$backend_drop" ]]; then cp -p "$backend_drop" "$release/backup/backend.conf"; backend_previous=1; fi
backend_was_running=0
frontend_was_stopped=0
frontend_moved=0
switched=0
restore() {
  status=$?
  trap - EXIT INT TERM
  if [[ "$switched" -eq 1 ]]; then
    set +e
    echo "Deployment failed; restoring previous code: $release" >&2
    if [[ "$frontend_was_stopped" -eq 1 ]]; then
      systemctl stop "$service"
      if [[ "$frontend_moved" -eq 1 ]]; then
        [[ ! -e "$live" ]] || mv "$live" "$release/failed-next"
        mv "$release/previous-next" "$live"
      fi
      systemctl start "$service"
    fi
    if [[ "$backend_previous" -eq 1 ]]; then cp -p "$release/backup/backend.conf" "$backend_drop"; else rm -f "$backend_drop"; fi
    systemctl daemon-reload
    [[ "$backend_was_running" -eq 0 ]] || systemctl restart finsentinel-backend
    echo 'Verified additive financial rows, if written, are retained; database dump remains in backup.' >&2
  fi
  exit "$status"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

switched=1
cat >"$backend_drop" <<EOF
[Service]
Environment=DATA_MODE=real_corpus
ExecStart=
ExecStart=/opt/finsentinel/.venv/bin/python -m uvicorn app.main:app --app-dir $release/backend --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips 127.0.0.1
EOF
systemctl daemon-reload
backend_was_running=1
systemctl restart finsentinel-backend
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 15 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health

sudo -u finsentinel env PYTHONPATH="$release/backend:$release" \
  DATABASE_URL='postgresql+psycopg:///finsentinel?host=/var/run/postgresql' \
  /opt/finsentinel/.venv/bin/python -m scripts.import_verified_financials \
  --database-url 'postgresql+psycopg:///finsentinel?host=/var/run/postgresql' \
  --corpus "$release/data/verified-financials/000157-2023-2024.jsonl" \
  --artifact-root /var/lib/finsentinel/ingestion | tee "$release/import-result.json"
grep -Fq '"metrics": 4' "$release/import-result.json"
sudo -u finsentinel env PYTHONPATH="$release/backend:$release" \
  DATABASE_URL='postgresql+psycopg:///finsentinel?host=/var/run/postgresql' \
  DATA_MODE=real_corpus \
  /opt/finsentinel/.venv/bin/python - <<'PY'
import os
from fastapi.testclient import TestClient
from app.main import create_app
app = create_app(database_url=os.environ['DATABASE_URL'])
with TestClient(app) as client:
    response = client.get('/api/v1/companies/000157/financial-analysis?from_period=2023FY&to_period=2024FY')
    body = response.json()
    if response.status_code != 200 or body.get('status') != 'completed' or len(body.get('evidence', [])) < 4:
        raise SystemExit('Post-import financial analysis acceptance failed')
    print('PASS post-import API: completed; evidence_count=' + str(len(body['evidence'])))
PY

frontend_was_stopped=1
systemctl stop "$service"
mv "$live" "$release/previous-next"
frontend_moved=1
cp -a "$release/frontend/.next" "$live"
systemctl start "$service"
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 15 --retry-connrefused --retry-delay 1 http://127.0.0.1:3000/companies/000157 >/dev/null
python3 - <<'PY'
from html.parser import HTMLParser
from urllib.request import ProxyHandler, Request, build_opener
opener = build_opener(ProxyHandler({}))
with opener.open(Request('http://127.0.0.1/companies/000157', headers={'Host':'120.24.108.60'}), timeout=15) as response:
    html = response.read().decode('utf-8')
    if response.status != 200:
        raise SystemExit('Nginx company research route failed financial analysis page check')
class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        value = attrs.get('href') if tag == 'link' else attrs.get('src') if tag == 'script' else None
        if value and value.startswith('/_next/'):
            self.paths.append(value)
parser = Parser()
parser.feed(html)
if not parser.paths:
    raise SystemExit('Nginx page has no Next.js asset references')
for path in parser.paths:
    with opener.open('http://127.0.0.1' + path, timeout=15) as asset:
        if asset.status != 200 or not asset.read(1):
            raise SystemExit(f'Nginx asset failed: {path}')
print('PASS nginx company 000157 route and ' + str(len(parser.paths)) + ' assets')
PY
nginx -t
for name in nginx finsentinel-backend finsentinel-frontend finsentinel-ingestion-worker finsentinel-query-encoder; do
  systemctl is-active --quiet "$name" || { echo "Service inactive: $name" >&2; exit 1; }
done
switched=0
trap - EXIT INT TERM
printf 'PASS deployment SOURCE_REVISION=%s\nRelease and database backup: %s\n' "$revision" "$release"
df -h /
