#!/usr/bin/env bash
# Run as root on the existing Ubuntu ECS host. No Git checkout, backend or Nginx changes.
set -euo pipefail
umask 022

readonly revision='c5596c87ce3942124996c174a32fec6a30b2d3aa'
readonly repository='zsr66666-creative/finsentinel-financial-agent'
readonly live='/opt/finsentinel/frontend/.next'
readonly service='finsentinel-frontend'

if [[ $EUID -ne 0 ]]; then
  echo 'Run this deployment script as root.' >&2
  exit 1
fi
for command in flock systemctl python3 sudo npm tar git; do
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
[[ -d "$live" && ! -L "$live" ]]
id finsentinel >/dev/null
install -d -o root -g root -m 755 /opt/finsentinel-releases
release="$(mktemp -d /opt/finsentinel-releases/research-desk-XXXXXXXX)"
chmod 755 "$release"
printf '%s\n' "$revision" >"$release/SOURCE_REVISION"
echo "Staging $revision in $release; the current frontend keeps serving."

python3 - "$revision" "$release" <<'PYARCHIVE'
import hashlib, io, sys, tarfile
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen
revision, destination = sys.argv[1:]
url = f'https://codeload.github.com/zsr66666-creative/finsentinel-financial-agent/tar.gz/{revision}'
with urlopen(Request(url, headers={'User-Agent':'FinSentinel-deploy'}), timeout=90) as response:
    data = response.read()
if hashlib.sha256(data).hexdigest() != '0a2f91e7632bcfb93bb837ad09119cf7fff6ff773fb6cb7f37b8ef86bc27649f':
    raise SystemExit('Source archive checksum mismatch')
root = Path(destination).resolve()
with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
    for member in archive.getmembers():
        parts = PurePosixPath(member.name).parts
        if len(parts) < 3 or parts[1] != 'frontend' or not member.isfile():
            continue
        relative = PurePosixPath(*parts[1:])
        if relative.is_absolute() or '..' in relative.parts:
            raise SystemExit('Unsafe archive path')
        target = root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.extractfile(member) as source:
            target.write_bytes(source.read())
print('PASS source archive SHA-256; staged pinned frontend')
PYARCHIVE

[[ -f "$release/frontend/package-lock.json" ]]
chown -R finsentinel:finsentinel "$release"
install -d -o finsentinel -g finsentinel -m 750 /var/lib/finsentinel/npm-cache
sudo -u finsentinel env NEXT_PUBLIC_API_URL='' NEXT_TELEMETRY_DISABLED=1 \
  bash -c 'cd "$1" && npm ci --cache /var/lib/finsentinel/npm-cache && npm test && npm run build' \
  _ "$release/frontend"

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

switch_started=0
rollback_on_exit() {
  status=$?
  trap - EXIT INT TERM
  if [[ "$switch_started" -eq 1 ]]; then
    set +e
    echo "Deployment failed; restoring the previous frontend. Release retained: $release" >&2
    systemctl stop "$service"
    rollback_failed=0
    if [[ -d "$release/previous-next" ]]; then
      if [[ -e "$live" || -L "$live" ]]; then
        mv "$live" "$release/failed-next" || rollback_failed=1
      fi
      if [[ "$rollback_failed" -eq 0 ]]; then
        mv "$release/previous-next" "$live" || rollback_failed=1
      fi
    fi
    # Also restart when stopping succeeded but moving the old build failed.
    systemctl start "$service" || rollback_failed=1
    if [[ "$rollback_failed" -eq 0 ]]; then
      echo 'Previous frontend restarted. Inspect the retained release before retrying.' >&2
    else
      echo "ROLLBACK ERROR: inspect $live and $release/previous-next immediately." >&2
    fi
    [[ "$status" -ne 0 ]] || status=1
  fi
  exit "$status"
}
trap rollback_on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

switch_started=1
systemctl stop "$service"
mv "$live" "$release/previous-next"
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
print('PASS localhost:3000/compare')

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

for path, expected in [('/', 'FinSentinel'), ('/compare', 'FinSentinel'), ('/login', 'FinSentinel'), ('/settings', 'FinSentinel'), ('/companies/002475', 'FinSentinel')]:
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

switch_started=0
trap - EXIT INT TERM
printf 'PASS deployment; SOURCE_REVISION=%s\nRetained release and backup: %s\n' "$revision" "$release"
