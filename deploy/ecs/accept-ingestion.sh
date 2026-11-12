#!/usr/bin/env bash
# Dedicated database acceptance. No injected faults in production.
set -euo pipefail
test "$(id -u)" = 0
cd /opt/finsentinel
stamp="$(date +%Y%m%d%H%M%S)"
testdb="finsentinel_fault_test_${stamp}"
restoredb="finsentinel_restore_test_${stamp}"
out="/var/lib/finsentinel/acceptance-${stamp}"
install -d -o finsentinel -g finsentinel -m 700 "$out"
sudo -u postgres createdb -O finsentinel "$testdb"
sudo -u postgres createdb -O finsentinel "$restoredb"
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d "$restoredb" -c 'CREATE EXTENSION IF NOT EXISTS vector;'
# Test dependencies only; no backend restart, no change to application dependencies.
python3 -m venv "$out/test-venv"
"$out/test-venv/bin/python" -m pip install -e './backend[postgres,dev]'
chown -R finsentinel:finsentinel "$out"
export PYTHONPATH=/opt/finsentinel/backend:/opt/finsentinel
export TEST_POSTGRES_URL="postgresql+psycopg:///${testdb}?host=/var/run/postgresql"
sudo -u finsentinel env PYTHONPATH="$PYTHONPATH" TEST_POSTGRES_URL="$TEST_POSTGRES_URL" \
 "$out/test-venv/bin/python" -m pytest backend/tests/test_ingestion_queue.py \
 backend/tests/test_ingestion_worker.py backend/tests/test_ingestion_download_policy.py \
 backend/tests/test_ingestion_task_api.py -q -p no:cacheprovider -o addopts='' \
 --junitxml="$out/tests.xml"
sudo -u finsentinel env PYTHONPATH="$PYTHONPATH" TEST_POSTGRES_URL="$TEST_POSTGRES_URL" \
 "$out/test-venv/bin/python" -m scripts.week05_worker_acceptance \
 --root "$out/worker" --output "$out/worker-result.json"
sudo -u finsentinel env PYTHONPATH="$PYTHONPATH" \
 /opt/finsentinel/.venv/bin/python -m scripts.ecs_restore_acceptance \
 --restore-db "$restoredb" --output-dir "$out/restore"
systemctl is-active finsentinel-backend finsentinel-frontend finsentinel-ingestion-worker
curl --fail --silent --show-error http://127.0.0.1:8000/health
echo
echo "Acceptance finished. Evidence: $out"
echo "Dedicated databases retained: $testdb $restoredb"
echo 'Production database was not restored or fault-injected. No services were restarted.'
