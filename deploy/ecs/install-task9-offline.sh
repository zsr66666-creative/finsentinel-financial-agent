#!/usr/bin/env bash
# Verified source-only package. Reuses the already deployed Task 8 ONNX runtime.
set -euo pipefail
umask 022
[[ $EUID -eq 0 ]] || { echo 'Run as root'; exit 1; }
package="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
task_name="${FINSENTINEL_CORPUS_DEPLOYMENT:-task9}"
case "$task_name" in
  task9) task_label='Task 9'; acceptance_module='scripts.task9_acceptance' ;;
  task10) task_label='Task 10'; acceptance_module='scripts.task10_acceptance' ;;
  *) echo 'Unknown corpus deployment'; exit 1 ;;
esac
root='/opt/finsentinel'
live="$root/frontend/.next"
nginx -t
for service in nginx finsentinel-backend finsentinel-frontend finsentinel-query-encoder; do
  systemctl is-active --quiet "$service"
done
systemctl show finsentinel-frontend -p ExecStart --value | grep -Fq "$live/standalone/server.js"
[[ -d "$live" && ! -L "$live" ]]
[[ -x "$root/.venv/bin/python" ]]
install -d -m 700 /run/lock/finsentinel-deploy
exec 9>/run/lock/finsentinel-deploy/research-desk.lock
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
python3 - "$package" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
for name,expected in json.loads((root/'PACKAGE_FILES.json').read_text()).items():
    path=(root/name).resolve()
    if not path.is_relative_to(root) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise SystemExit('Package checksum mismatch: '+name)
print('PASS corpus package integrity')
PY
encoder_release="$(systemctl show finsentinel-query-encoder -p WorkingDirectory --value)"
[[ "$encoder_release" == /opt/finsentinel-releases/* ]]
encoder_python="$encoder_release/encoder-venv/bin/python"
model_dir="$encoder_release/model"
[[ -x "$encoder_python" && -f "$model_dir/manifest.json" ]]
available_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
[[ "$available_kib" -ge 716800 ]] || { echo 'Less than 700 MiB available; stop and inspect memory'; exit 1; }
install -d -m 755 /opt/finsentinel-releases
release="$(mktemp -d /opt/finsentinel-releases/"$task_name"-corpus-XXXXXXXX)"
chmod 755 "$release"
cp -a "$package/backend" "$package/frontend" "$package/scripts" "$release/"
cp "$package/SOURCE_REVISION" "$release/"
if [[ -d "$package/data" ]]; then cp -a "$package/data" "$release/"; fi
chown -R finsentinel:finsentinel "$release"
echo "Staging $task_label: $release; current website keeps serving"
install -d -o finsentinel -g finsentinel -m 750 /var/lib/finsentinel/npm-cache
sudo -u finsentinel env NEXT_PUBLIC_API_URL='' NEXT_TELEMETRY_DISABLED=1 \
  bash -c 'cd "$1" && npm ci --cache /var/lib/finsentinel/npm-cache && npm test && npm run build' _ "$release/frontend"
standalone="$release/frontend/.next/standalone"
[[ -f "$standalone/server.js" ]]
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
mkdir -p "$standalone/.next"
cp -a "$release/frontend/.next/static" "$standalone/.next/"
if [[ -d "$release/frontend/public" ]]; then cp -a "$release/frontend/public" "$standalone/"; fi
cp "$release/SOURCE_REVISION" "$release/frontend/.next/SOURCE_REVISION"
chown -R finsentinel:finsentinel "$release/frontend/.next"
install -d -m 700 "$release/backup"
sudo -u postgres pg_dump -Fc -d finsentinel > "$release/backup/database.dump"
chmod 600 "$release/backup/database.dump"
test -s "$release/backup/database.dump"
echo 'PASS pre-index database backup'
backend_drop='/etc/systemd/system/finsentinel-backend.service.d/90-task9-corpus.conf'
mkdir -p /etc/systemd/system/finsentinel-backend.service.d
backend_previous=0
if [[ -f "$backend_drop" ]]; then cp -p "$backend_drop" "$release/backup/backend.conf"; backend_previous=1; fi
switch_started=0
frontend_stopped=0
frontend_moved=0
encoder_stopped=0
rollback() {
  status=$?
  trap - EXIT INT TERM
  set +e
  if [[ "$encoder_stopped" -eq 1 ]]; then systemctl start finsentinel-query-encoder; fi
  if [[ "$switch_started" -eq 1 ]]; then
    echo "Deployment failed; restoring previous services. Retained release: $release" >&2
    if [[ "$frontend_stopped" -eq 1 ]]; then
      systemctl stop finsentinel-frontend
      if [[ "$frontend_moved" -eq 1 ]]; then
        if [[ -d "$live" ]]; then mv "$live" "$release/failed-next"; fi
        mv "$release/previous-next" "$live"
      fi
      systemctl start finsentinel-frontend
    fi
    if [[ "$backend_previous" -eq 1 ]]; then cp -p "$release/backup/backend.conf" "$backend_drop"; else rm -f "$backend_drop"; fi
    systemctl daemon-reload
    systemctl restart finsentinel-backend
    [[ "$status" -ne 0 ]] || status=1
  fi
  if [[ "$status" -ne 0 ]]; then
    echo 'Any successfully committed additive index is retained; existing evidence was not overwritten.' >&2
    echo "Database backup and diagnostics: $release" >&2
  fi
  exit "$status"
}
trap rollback EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
run_admin() {
  sudo -u finsentinel env PYTHONPATH="$release/backend:$release" \
    DATABASE_URL='postgresql+psycopg:///finsentinel?host=/var/run/postgresql' \
    "$root/.venv/bin/python" "$@"
}
# Acquisition remains in the existing persistent queue; no admin token is exposed.
artifact_ids=(05e081ae37a01bc1df83183f2b93c64590d2c2aac6dd4d0c9864743de1b105c4)
if [[ "$task_name" == task10 ]]; then
  systemctl is-active --quiet finsentinel-ingestion-worker
  run_admin -m scripts.task10_acquire --output "$release/acquisition.json"
  python3 - "$release/acquisition.json" > "$release/artifact-ids.txt" <<'PY'
import json,re,sys
ids=json.load(open(sys.argv[1]))['artifact_ids']
assert len(ids)==2 and len(set(ids))==2 and all(re.fullmatch('[0-9a-f]{64}',item) for item in ids)
print('\n'.join(ids))
PY
  mapfile -t artifact_ids < "$release/artifact-ids.txt"
fi
# Validate actual PDF text before briefly pausing online encoding.
run_admin - "${artifact_ids[@]}" <<'PY'
from sqlalchemy import create_engine
import os,sys
from scripts.task9_index import load_chunks
engine=create_engine(os.environ['DATABASE_URL'])
try:
    for identity in sys.argv[1:]:
        chunks=load_chunks(engine,identity,'/var/lib/finsentinel/ingestion')
        print('PASS source PDF, parsed text and physical offsets:',identity,len(chunks),'chunks')
finally:engine.dispose()
PY
encoder_stopped=1
systemctl stop finsentinel-query-encoder
for artifact in "${artifact_ids[@]}"; do
  for pass in first repeat; do
    run_admin -m scripts.task9_index \
      --artifact-id "$artifact" \
      --artifact-root /var/lib/finsentinel/ingestion --encoder-python "$encoder_python" \
      --model-dir "$model_dir" --output "$release/index-$artifact-$pass.json"
  done
  python3 - "$release/index-$artifact-first.json" "$release/index-$artifact-repeat.json" <<'PY'
import json,sys
first,repeat=[json.load(open(path)) for path in sys.argv[1:]]
assert first['total']>0 and repeat['inserted']==0 and repeat['existing']==first['total']
print('PASS idempotent publication:',first['total'],'chunks')
PY
done
systemctl start finsentinel-query-encoder
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8081/health
encoder_stopped=0
switch_started=1
cat > "$backend_drop" <<EOF
[Service]
Environment="QUERY_ENCODER_ENABLED=1"
ExecStart=
ExecStart=$root/.venv/bin/python -m uvicorn app.main:app --app-dir $release/backend --host 127.0.0.1 --port 8000
EOF
systemctl daemon-reload
systemctl restart finsentinel-backend
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:8000/health
run_admin -m "$acceptance_module" --output "$release/api-acceptance.json"
frontend_stopped=1
systemctl stop finsentinel-frontend
mv "$live" "$release/previous-next"
frontend_moved=1
cp -a "$release/frontend/.next" "$live"
systemctl start finsentinel-frontend
curl --noproxy '*' --fail --silent --show-error --max-time 10 --retry 10 --retry-connrefused --retry-delay 1 http://127.0.0.1:3000/compare >/dev/null
python3 - <<'PY'
import os
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
routes=['/','/compare','/login','/settings','/companies/002475']
if os.environ.get('FINSENTINEL_CORPUS_DEPLOYMENT')=='task10':routes+=['/companies/002555','/companies/002230']
for route in routes:
    html=fetch(route).decode();assert 'FinSentinel' in html
    assets=Assets();assets.feed(html);assert assets.paths
    for path in assets.paths:assert fetch(path)
    print('PASS Nginx application shell and assets:',route)
PY
run_admin -m "$acceptance_module" --api-url http://127.0.0.1 --host-header 120.24.108.60 --output "$release/nginx-acceptance.json"
systemctl is-active finsentinel-backend finsentinel-frontend finsentinel-ingestion-worker finsentinel-query-encoder
systemctl show finsentinel-query-encoder -p ActiveState -p NRestarts -p MemoryCurrent -p MemoryPeak
switch_started=0
trap - EXIT INT TERM
echo "PASS $task_label deployment; retained release and backup: $release"
echo 'Browser company/period switching, keyboard/mobile and theme checks still need manual acceptance.'
