#!/usr/bin/env bash
# Run as root on the existing Ubuntu ECS host. No Git checkout, backend or Nginx changes.
set -euo pipefail
umask 022

readonly revision='f385056bf52dc7b521ada6f8e5015c7f77acb904'
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
[[ -d "$live" && ! -L "$live" ]]
id finsentinel >/dev/null
install -d -o root -g root -m 755 /opt/finsentinel-releases
release="$(mktemp -d /opt/finsentinel-releases/research-desk-XXXXXXXX)"
chmod 755 "$release"
printf '%s\n' "$revision" >"$release/SOURCE_REVISION"
echo "Staging $revision in $release; the current frontend keeps serving."

if git -C /opt/finsentinel cat-file -e "$revision^{commit}" 2>/dev/null; then
  git -C /opt/finsentinel archive "$revision" frontend | tar -xf - -C "$release"
else
  # GitHub API works independently of the host's Git/SSH transport. Every downloaded
  # blob is checked against the immutable commit's tree; no credentials are used.
  python3 - "$repository" "$revision" "$release" <<'PY'
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import time
from urllib.request import Request, urlopen

repository, revision, destination = sys.argv[1:]
root = Path(destination).resolve()
base = f'https://api.github.com/repos/{repository}/git/'

def get_json(endpoint):
    for attempt in range(3):
        try:
            request = Request(base + endpoint, headers={
                'Accept': 'application/vnd.github+json',
                'User-Agent': 'FinSentinel-pinned-frontend-deploy',
                'X-GitHub-Api-Version': '2022-11-28',
            })
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)

tree = get_json(f'trees/{revision}?recursive=1')
if tree.get('truncated') or not isinstance(tree.get('tree'), list):
    raise RuntimeError('GitHub did not return a complete source tree')
entries = [entry for entry in tree['tree']
           if entry.get('path', '').startswith('frontend/') and entry.get('type') != 'tree']
if not 1 <= len(entries) <= 20:
    raise RuntimeError(f'Unexpected frontend file count: {len(entries)} (expected at most 20)')
seen = set()
for entry in entries:
    name = entry['path']
    path = PurePosixPath(name)
    sha = entry.get('sha', '')
    if (entry.get('type') != 'blob' or entry.get('mode') not in ('100644', '100755')
            or path.is_absolute() or '\\' in name or ':' in name
            or any(part in ('', '.', '..', '.git') for part in name.split('/'))
            or str(path) != name or name in seen
            or not re.fullmatch(r'[0-9a-f]{40}', sha)):
        raise RuntimeError(f'Unsafe or unsupported source entry: {name!r}')
    seen.add(name)
    target = root.joinpath(*path.parts)
    if root not in target.resolve().parents:
        raise RuntimeError(f'Path escapes release directory: {name!r}')
    blob = get_json(f'blobs/{sha}')
    if blob.get('encoding') != 'base64':
        raise RuntimeError(f'Unexpected blob encoding: {name}')
    data = base64.b64decode(''.join(blob['content'].split()), validate=True)
    digest = hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()
    if digest != sha or blob.get('sha') != sha or len(data) != entry.get('size'):
        raise RuntimeError(f'Git blob verification failed: {name}')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(0o755 if entry['mode'] == '100755' else 0o644)
print(f'Verified {len(entries)} frontend blobs from {revision}')
PY
fi

[[ -f "$release/frontend/package-lock.json" ]]
chown -R finsentinel:finsentinel "$release"
install -d -o finsentinel -g finsentinel -m 750 /var/lib/finsentinel/npm-cache
sudo -u finsentinel env NEXT_PUBLIC_API_URL='' NEXT_TELEMETRY_DISABLED=1 \
  bash -c 'cd "$1" && npm ci --cache /var/lib/finsentinel/npm-cache && npm run build' \
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
        if '应收账款变动核对' not in html:
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

for path, expected in [('/', 'FinSentinel'), ('/compare', '应收账款变动核对')]:
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
