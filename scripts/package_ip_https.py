"""Build a small committed source-only IP HTTPS installation archive."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import subprocess
import tarfile

FILES = ('deploy/ecs/install-ip-https.sh', 'scripts/ip_https.py',
         'docs/free-ip-https.md', 'backend/tests/test_ip_https.py')


def package(output, revision='HEAD'):
    root = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(['git', 'rev-parse', revision+'^{commit}'], cwd=root, text=True).strip()
    files = {name: subprocess.check_output(['git', 'show', commit+':'+name], cwd=root) for name in FILES}
    assert b'\r' not in files[FILES[0]], 'Shell must use LF'
    files['SOURCE_REVISION'] = (commit+'\n').encode()
    files['SHA256SUMS'] = ''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n'
                                 for name, data in sorted(files.items())).encode()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('wb') as stream, gzip.GzipFile(filename='', fileobj=stream, mode='wb', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w|') as archive:
            for name, data in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o755 if name.endswith('.sh') else 0o644
                archive.addfile(info, io.BytesIO(data))
    with tarfile.open(output, 'r:gz') as archive:
        assert {e.name: archive.extractfile(e).read() for e in archive} == files
    print(f'{hashlib.sha256(output.read_bytes()).hexdigest()}  {output}')
    print(f'SOURCE_REVISION={commit}; files={len(files)}; bytes={output.stat().st_size}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--revision', default='HEAD')
    args = parser.parse_args()
    package(args.output, args.revision)
