#!/usr/bin/env bash
# Run as root, from the reviewed checkout. Never prints the management token.
set -euo pipefail
test "$(id -u)" = 0
cd /opt/finsentinel
test -x .venv/bin/python
backup="/root/finsentinel-ingestion-backup-$(date +%Y%m%d-%H%M%S)"
install -d -m 700 "$backup"
git rev-parse HEAD > "$backup/commit.txt"
systemctl cat finsentinel-backend > "$backup/backend-unit.txt"
sudo -u postgres pg_dump -Fc finsentinel > "$backup/finsentinel.dump"
test -s "$backup/finsentinel.dump"
sudo -u postgres pg_restore --list < "$backup/finsentinel.dump" > "$backup/dump-list.txt"
echo "Backup verified readable: $backup (restore drill not performed)"

.venv/bin/python -m pip check
sudo -u finsentinel env PYTHONPATH=/opt/finsentinel/backend:/opt/finsentinel \
  .venv/bin/python - <<'PY'
from sqlalchemy import create_engine
from app.migrations import migrate_ingestion_up, migrate_artifacts_up
engine=create_engine('postgresql+psycopg:///finsentinel?host=/var/run/postgresql')
print('queue:',migrate_ingestion_up(engine))
print('artifacts:',migrate_artifacts_up(engine))
print('repeat:',migrate_ingestion_up(engine),migrate_artifacts_up(engine))
engine.dispose()
PY

install -d -o finsentinel -g finsentinel -m 700 /var/lib/finsentinel/ingestion
install -d -m 700 /etc/finsentinel
if [ ! -e /etc/finsentinel/ingestion.env ]; then
  (umask 077; .venv/bin/python - <<'PY'
import secrets
from pathlib import Path
Path('/etc/finsentinel/ingestion.env').write_text('INGESTION_ADMIN_TOKEN='+secrets.token_urlsafe(48)+'\n')
PY
  )
fi
chmod 600 /etc/finsentinel/ingestion.env
install -d /etc/systemd/system/finsentinel-backend.service.d
printf '[Service]\nEnvironmentFile=/etc/finsentinel/ingestion.env\n' \
  > /etc/systemd/system/finsentinel-backend.service.d/ingestion.conf
install -m 644 deploy/ecs/finsentinel-ingestion-worker.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart finsentinel-backend
curl --fail --silent --show-error --retry 8 --retry-connrefused --retry-delay 2 http://127.0.0.1:8000/health
echo
# Worker is intentionally NOT started until operator completes a single-job check.
echo 'Prepared. Worker is not enabled or started. Next: authenticated loopback enqueue and --once acceptance.'
echo "Rollback reference: $backup"
