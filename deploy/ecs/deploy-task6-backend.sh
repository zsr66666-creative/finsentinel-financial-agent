#!/usr/bin/env bash
set -euo pipefail
revision='0bdb061c3aa226c0af07751409d3308de6be11ad'
repo='zsr66666-creative/finsentinel-financial-agent'
root='/opt/finsentinel'
service='finsentinel-backend'
[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 1; }
command -v python3 >/dev/null; command -v systemctl >/dev/null
systemctl is-active --quiet "$service"
release="$(mktemp -d /opt/finsentinel-releases/task6-backend-XXXXXXXX)"
trap 'rm -rf "$release"' EXIT
python3 - "$repo" "$revision" "$release" <<'PY'
import base64, hashlib, json, sys
from pathlib import Path
from urllib.request import Request, urlopen
repo, rev, out = sys.argv[1:]
files = ('backend/app/main.py', 'backend/app/schemas.py')
for name in files:
    url = f'https://api.github.com/repos/{repo}/contents/{name}?ref={rev}'
    with urlopen(Request(url, headers={'User-Agent':'FinSentinel-task6'}), timeout=30) as r:
        item=json.load(r)
    data=base64.b64decode(item['content'])
    expected=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if expected != item['sha']:
        raise SystemExit(f'blob verification failed: {name}')
    target=Path(out)/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data)
PY
backup="$release/backend-backup"
mkdir -p "$backup/backend/app"
cp -p "$root/backend/app/main.py" "$root/backend/app/schemas.py" "$backup/backend/app/"
cp -p "$release/backend/app/main.py" "$root/backend/app/main.py"
cp -p "$release/backend/app/schemas.py" "$root/backend/app/schemas.py"
chown finsentinel:finsentinel "$root/backend/app/main.py" "$root/backend/app/schemas.py"
if ! systemctl restart "$service"; then
  cp -p "$backup/backend/app/main.py" "$root/backend/app/main.py"
  cp -p "$backup/backend/app/schemas.py" "$root/backend/app/schemas.py"
  systemctl restart "$service" || true
  exit 1
fi
if ! curl --fail --silent --show-error --max-time 15 --retry 8 --retry-connrefused --retry-delay 2 http://127.0.0.1:8000/health >/dev/null; then
  cp -p "$backup/backend/app/main.py" "$root/backend/app/main.py"
  cp -p "$backup/backend/app/schemas.py" "$root/backend/app/schemas.py"
  systemctl restart "$service" || true
  exit 1
fi
echo "PASS backend Task 6 revision=$revision backup=$backup"
