#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root" >&2
  exit 1
fi
if [[ "$#" -ne 2 ]]; then
  echo "Usage: $0 BACKUP_ID 'ssh-ed25519 AAAA... comment'" >&2
  exit 2
fi

backup_id="$1"
public_key="$2"
if [[ "$public_key" == *$'\n'* || "$public_key" == *$'\r'* ]]; then
  echo "Public key must be exactly one line" >&2
  exit 2
fi
if [[ ! "$backup_id" =~ ^backup-[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}$ ]]; then
  echo "Invalid backup ID" >&2
  exit 2
fi
if [[ ! "$public_key" =~ ^ssh-ed25519[[:space:]]+[A-Za-z0-9+/=]+([[:space:]].*)?$ ]]; then
  echo "Expected one Ed25519 public key" >&2
  exit 2
fi
key_check="$(mktemp /root/.restore-key-check-XXXXXXXX)"
trap 'rm -f -- "$key_check"' EXIT
printf '%s\n' "$public_key" > "$key_check"
if ! ssh-keygen -lf "$key_check" >/dev/null; then
  echo "Invalid Ed25519 public key" >&2
  exit 2
fi
rm -f -- "$key_check"
trap - EXIT

authorized_keys=/root/.ssh/authorized_keys
receiver=/usr/local/sbin/finsentinel-offsite-restore-once
ops_python=/opt/finsentinel-operations-venv/bin/python
inbox=/var/lib/finsentinel/restore-drill-inbox
source_receiver="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/scripts/offsite_restore_receiver.py"
source_verifier="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/scripts/verify_offsite_archive.py"

test -f "$authorized_keys" && test ! -L "$authorized_keys"
test -f "$source_receiver" && test -f "$source_verifier"
test -x "$ops_python"
install -d -o root -g root -m 700 "$inbox"
free_bytes="$(df --output=avail -B1 "$inbox" | tail -n 1 | tr -d '[:space:]')"
if [[ ! "$free_bytes" =~ ^[0-9]+$ ]] || (( free_bytes < 3221225472 )); then
  echo "At least 3 GiB free space is required for the restore drill" >&2
  exit 1
fi
install -o root -g root -m 700 "$source_receiver" "$receiver"
install -o root -g root -m 644 "$source_verifier" "$(dirname "$receiver")/verify_offsite_archive.py"

comment="finsentinel-restore-drill-${backup_id}"
key_line="restrict,command=\"${ops_python} ${receiver} ${backup_id}\" ${public_key} ${comment}"
if grep -Fq "$comment" "$authorized_keys"; then
  if ! grep -Fxq "$key_line" "$authorized_keys"; then
    echo "A different key for this backup ID is already installed" >&2
    exit 1
  fi
else
  if [[ -s "$authorized_keys" ]] && [[ "$(tail -c 1 "$authorized_keys" | wc -l)" -eq 0 ]]; then
    printf '\n' >> "$authorized_keys"
  fi
  printf '%s\n' "$key_line" >> "$authorized_keys"
fi
chown root:root "$authorized_keys"
chmod 600 "$authorized_keys"

echo "One-shot restricted key installed for ${backup_id}. It can only invoke the restore receiver and is removed by the receiver after one attempt."
echo "Start the Windows sender now; no sshd reload is needed."
