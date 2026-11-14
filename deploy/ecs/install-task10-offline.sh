#!/usr/bin/env bash
set -euo pipefail
export FINSENTINEL_CORPUS_DEPLOYMENT=task10
directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bash -n "$directory/install-task9-offline.sh"
exec bash "$directory/install-task9-offline.sh"
