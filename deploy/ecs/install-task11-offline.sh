#!/usr/bin/env bash
set -euo pipefail
package="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export FINSENTINEL_CORPUS_DEPLOYMENT=task11
bash -n "$package/deploy/ecs/install-task9-offline.sh"
exec bash "$package/deploy/ecs/install-task9-offline.sh"
