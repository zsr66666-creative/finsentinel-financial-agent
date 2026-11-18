"""Validate and stream one Windows offsite backup to its forced ECS receiver."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from scripts.verify_offsite_archive import verify_archive
from scripts.windows_offsite_pull import _verify_age_stream

BACKUP_RE = re.compile(r'backup-\d{8}T\d{12}Z-[0-9a-f]{32}\Z')


def validate_local_copy(ciphertext, index_path):
    ciphertext = Path(ciphertext)
    index_path = Path(index_path)
    try:
        if ciphertext.is_symlink() or index_path.is_symlink():
            raise ValueError()
        data = json.loads(index_path.read_text(encoding='utf-8'))
        backup_id = data['backup_id']
        if (not isinstance(backup_id, str) or not BACKUP_RE.fullmatch(backup_id)
                or data['filename'] != ciphertext.name
                or data['schema_version'] != 1
                or type(data['ciphertext_size']) is not int):
            raise ValueError()
        digest = hashlib.sha256()
        size = 0
        with ciphertext.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                size += len(block)
                digest.update(block)
        if size != data['ciphertext_size'] or digest.hexdigest() != data['ciphertext_sha256']:
            raise ValueError()
        return backup_id
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('ciphertext_integrity_failed') from None


def send_restore(ciphertext, index_path, identity, ssh_key, known_hosts, *,
                 server='120.24.108.60', age_exe='age.exe', ssh_exe='ssh.exe'):
    backup_id = validate_local_copy(ciphertext, index_path)
    age_path = Path(age_exe).resolve()
    age_command = str(age_path) if age_path.is_file() else age_exe
    _verify_age_stream(Path(ciphertext), Path(identity), subprocess.Popen,
                       verify_archive, age_exe=age_command)
    encrypted = Path(ciphertext).open('rb')
    age = ssh = None
    try:
        age = subprocess.Popen([age_exe, '--decrypt', '--identity', str(identity)],
                               stdin=encrypted, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=os.environ.copy())
        ssh_args = [ssh_exe, '-T', '-i', str(ssh_key), '-oBatchMode=yes',
                    '-oIdentitiesOnly=yes', '-oStrictHostKeyChecking=yes',
                    '-oHostKeyAlgorithms=ssh-ed25519', '-oUserKnownHostsFile=' + str(known_hosts),
                    '-oConnectTimeout=10', 'root@' + server, 'restore ' + backup_id]
        ssh = subprocess.Popen(ssh_args, stdin=age.stdout)
        age.stdout.close()
        ssh_code = ssh.wait(timeout=3600)
        age_code = age.wait(timeout=30)
        if ssh_code != 0 or age_code != 0:
            raise RuntimeError('restore_transfer_failed')
        return backup_id
    except Exception:
        for process in (ssh, age):
            if process is not None and process.poll() is None:
                process.kill()
        raise RuntimeError('restore_transfer_failed') from None
    finally:
        encrypted.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ciphertext', required=True)
    parser.add_argument('--index', required=True)
    parser.add_argument('--identity', required=True)
    parser.add_argument('--ssh-key', required=True)
    parser.add_argument('--known-hosts', required=True)
    parser.add_argument('--server', default='120.24.108.60')
    parser.add_argument('--age-exe', default='age.exe')
    parser.add_argument('--ssh-exe', default='ssh.exe')
    args = parser.parse_args(argv)
    try:
        backup_id = send_restore(args.ciphertext, args.index, args.identity,
            args.ssh_key, args.known_hosts, server=args.server,
            age_exe=args.age_exe, ssh_exe=args.ssh_exe)
    except (ValueError, RuntimeError) as exc:
        print('restore_transfer: failed ' + str(exc), file=sys.stderr)
        return 1
    print('restore_transfer: sent ' + backup_id)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
