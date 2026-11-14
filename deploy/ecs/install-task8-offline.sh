#!/usr/bin/env bash
# Run from the verified private task8 package as root. No git/HuggingFace access.
set -euo pipefail
umask 022
[[ $EUID -eq 0 ]] || { echo 'Run as root'; exit 1; }
package="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
root='/opt/finsentinel'
live="$root/frontend/.next"
nginx -t
systemctl is-active --quiet nginx
systemctl is-active --quiet finsentinel-backend
systemctl is-active --quiet finsentinel-frontend
systemctl show finsentinel-frontend -p ExecStart --value | grep -Fq "$live/standalone/server.js"
[[ -d "$live" && ! -L "$live" ]]
install -d -m 700 /run/lock/finsentinel-deploy
exec 9>/run/lock/finsentinel-deploy/research-desk.lock
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
python3 - "$package" <<'PY'
import hashlib, json, sys
from pathlib import Path
root=Path(sys.argv[1])
for name, expected in json.loads((root/'PACKAGE_FILES.json').read_text()).items():
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise SystemExit('Invalid package path')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise SystemExit('Package checksum mismatch: '+name)
print('PASS private package file checksums')
PY
# Leave room for npm build plus the old running services. MemAvailable includes cache.
available_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
[[ "$available_kib" -ge 716800 ]] || { echo 'Less than 700 MiB available; stop and inspect memory'; exit 1; }
install -d -m 755 /opt/finsentinel-releases
release="$(mktemp -d /opt/finsentinel-releases/task8-online-XXXXXXXX)"
chmod 755 "$release"
cp -a "$package/backend" "$package/frontend" "$package/scripts" "$package/model" "$release/"
cp "$package/SOURCE_REVISION" "$release/"
chown -R finsentinel:finsentinel "$release"
echo "Staging Task 8 in $release; current website keeps serving"
install -d -o finsentinel -g finsentinel -m 750 /var/lib/finsentinel/npm-cache
sudo -u finsentinel env NEXT_PUBLIC_API_URL='' NEXT_TELEMETRY_DISABLED=1 \
  bash -c 'cd "$1" && npm ci --cache /var/lib/finsentinel/npm-cache && npm test && npm run build' _ "$release/frontend"
python3 -m venv "$release/encoder-venv"
"$release/encoder-venv/bin/pip" install --disable-pip-version-check \
  'onnxruntime>=1.20,<2' 'tokenizers>=0.21,<1' 'numpy>=1.26,<3' 'psutil>=6,<8' 'requests>=2.32,<3'
chown -R finsentinel:finsentinel "$release/encoder-venv"
# Run genuine parity and memory measurements before exposing online retrieval.
sudo -u finsentinel "$release/encoder-venv/bin/python" "$release/scripts/task8_cpu_assessment.py" benchmark --directory "$release/model"
python3 - "$release/model/assessment.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
if not r['parity_passed'] or r['imported_torch'] or r['peak_mib']>384:
    raise SystemExit('CPU parity/memory acceptance failed')
print('PASS Linux CPU parity, no torch, peak MiB:',r['peak_mib'])
PY

backend_drop='/etc/systemd/system/finsentinel-backend.service.d/80-task8-online.conf'
encoder_unit='/etc/systemd/system/finsentinel-query-encoder.service'
mkdir -p "$release/backup" /etc/systemd/system/finsentinel-backend.service.d
backend_previous=0
encoder_previous=0
encoder_was_active=0
if [[ -f "$backend_drop" ]]; then cp -p "$backend_drop" "$release/backup/backend.conf"; backend_previous=1; fi
if [[ -f "$encoder_unit" ]]; then cp -p "$encoder_unit" "$release/backup/encoder.service"; encoder_previous=1; fi
if systemctl is-active --quiet finsentinel-query-encoder; then encoder_was_active=1; fi
switch_started=0
frontend_stopped=0
frontend_moved=0
rollback() {
  status=$?
  trap - EXIT INT TERM
  if [[ "$switch_started" -eq 1 ]]; then
    set +e
    echo "Deployment failed; restoring previous services. Release retained: $release" >&2
    if [[ "$frontend_stopped" -eq 1 ]]; then
      systemctl stop finsentinel-frontend
      if [[ "$frontend_moved" -eq 1 ]]; then
        if [[ -d "$live" ]]; then mv "$live" "$release/failed-next"; fi
        mv "$release/previous-next" "$live"
      fi
      systemctl start finsentinel-frontend
    fi
    if [[ "$backend_previous" -eq 1 ]]; then cp -p "$release/backup/backend.conf" "$backend_drop"; else rm -f "$backend_drop"; fi
    systemctl stop finsentinel-query-encoder
    if [[ "$encoder_previous" -eq 1 ]]; then cp -p "$release/backup/encoder.service" "$encoder_unit"; else rm -f "$encoder_unit"; fi
    systemctl daemon-reload
    systemctl restart finsentinel-backend
    if [[ "$encoder_was_active" -eq 1 ]]; then systemctl start finsentinel-query-encoder; fi
    [[ "$status" -ne 0 ]] || status=1
  fi
  exit "$status"
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
switch_started=1
cat > "$encoder_unit" <<EOF
[Unit]
Description=FinSentinel pinned BGE query encoder (loopback CPU)
After=network.target
[Service]
User=finsentinel
Group=finsentinel
WorkingDirectory=$release
Environment="PYTHONPATH=$release/backend"
Environment="QUERY_ENCODER_MODEL_DIR=$release/model"
Environment="OMP_NUM_THREADS=1"
ExecStart=$release/encoder-venv/bin/python -m app.query_encoder_service
Restart=on-failure
RestartSec=5
MemoryHigh=384M
MemoryMax=512M
TasksMax=64
NoNewPrivileges=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
EOF
cat > "$backend_drop" <<EOF
[Service]
Environment="QUERY_ENCODER_ENABLED=1"
ExecStart=
ExecStart=$root/.venv/bin/python -m uvicorn app.main:app --app-dir $release/backend --host 127.0.0.1 --port 8000
EOF
systemctl daemon-reload
systemctl restart finsentinel-query-encoder
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8081/health
systemctl restart finsentinel-backend
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health
sudo -u finsentinel "$release/encoder-venv/bin/python" "$release/scripts/task8_online_acceptance.py" \
  --model-dir "$release/model" --api-url http://127.0.0.1:8000 --output "$release/cloud-acceptance.json"
# Recheck the original reviewed comparison before any frontend switch.
"$release/encoder-venv/bin/python" - <<'PY'
import requests
s=requests.Session();s.trust_env=False
r=s.post('http://127.0.0.1:8000/api/v1/evidence/compare',json={'question':'立讯精密2026年6月30日母公司应收账款较2025年12月31日是否未增加？'},timeout=15)
r.raise_for_status();body=r.json()
assert body['status']=='supported' and body['claim_true'] is True
print('PASS original reviewed comparison')
PY
python3 - "$live/static" "$release/frontend/.next/static" <<'PY'
import os,shutil,sys
from pathlib import Path
old,new=map(Path,sys.argv[1:])
for directory,_,names in os.walk(old,followlinks=False):
    for name in names:
        source=Path(directory)/name
        if source.is_symlink():continue
        target=new/source.relative_to(old)
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
PY
standalone="$release/frontend/.next/standalone"
[[ -f "$standalone/server.js" ]]
mkdir -p "$standalone/.next"
cp -a "$release/frontend/.next/static" "$standalone/.next/"
if [[ -d "$release/frontend/public" ]]; then cp -a "$release/frontend/public" "$standalone/"; fi
cp "$release/SOURCE_REVISION" "$release/frontend/.next/SOURCE_REVISION"
chown -R finsentinel:finsentinel "$release/frontend/.next"
frontend_stopped=1
systemctl stop finsentinel-frontend
mv "$live" "$release/previous-next"
frontend_moved=1
cp -a "$release/frontend/.next" "$live"
systemctl start finsentinel-frontend
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:3000/compare >/dev/null
python3 - <<'PY'
from html.parser import HTMLParser
from urllib.request import Request,ProxyHandler,build_opener
from urllib.parse import urlsplit
opener=build_opener(ProxyHandler({}))
def fetch(path):
    with opener.open(Request('http://127.0.0.1'+path,headers={'Host':'120.24.108.60'}),timeout=15) as r:
        assert r.status==200
        return r.read()
class Assets(HTMLParser):
    def __init__(self):super().__init__();self.paths=set()
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);value=attrs.get('src') if tag=='script' else attrs.get('href') if tag=='link' else None
        if value and urlsplit(value).path.endswith(('.js','.css')):
            assert value.startswith('/_next/')
            self.paths.add(value)
for route in ['/','/compare','/login','/settings','/companies/002475']:
    html=fetch(route).decode();assert 'FinSentinel' in html
    assets=Assets();assets.feed(html);assert assets.paths
    for path in assets.paths:assert fetch(path)
    print('PASS Nginx application shell and assets:',route)
PY
sudo -u finsentinel "$release/encoder-venv/bin/python" "$release/scripts/task8_online_acceptance.py" \
  --model-dir "$release/model" --api-url http://127.0.0.1 --host-header 120.24.108.60 --output "$release/nginx-acceptance.json"
systemctl enable finsentinel-query-encoder
systemctl show finsentinel-query-encoder -p ActiveState -p NRestarts -p MemoryCurrent -p MemoryPeak
switch_started=0
trap - EXIT INT TERM
echo "PASS Task 8 deployment; retained release and backup: $release"
echo 'Browser text-search interaction still needs manual acceptance.'
