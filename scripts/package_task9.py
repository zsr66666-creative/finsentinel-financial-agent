"""Build a source-only, checksum-verified ECS archive from committed git blobs."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile


def package(output, revision='HEAD'):
    root = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(['git', 'rev-parse', revision + '^{commit}'], cwd=root, text=True).strip()
    exported = subprocess.check_output(['git', 'archive', '--format=tar', commit, 'backend', 'frontend', 'scripts',
        'deploy/ecs/install-task9-offline.sh', 'docs/task9-corpus-expansion.md'], cwd=root)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(exported), mode='r:') as archive:
        for member in archive.getmembers():
            if member.isdir(): continue
            path = PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or '..' in path.parts:
                raise ValueError('unsafe git archive entry')
            data = archive.extractfile(member).read()
            if member.name.endswith('.sh') and b'\r' in data:
                raise ValueError('Shell scripts must retain LF in the actual archive: ' + member.name)
            files[member.name] = data
    files['SOURCE_REVISION'] = (commit + '\n').encode()
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    files['PACKAGE_FILES.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('wb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w|') as archive:
            for name, data in sorted(files.items()):
                member = tarfile.TarInfo(name)
                member.size = len(data)
                member.mode = 0o755 if name.endswith('.sh') else 0o644
                archive.addfile(member, io.BytesIO(data))
    report = dict(path=str(output), source_revision=commit, files=len(files), bytes=output.stat().st_size,
                  sha256=hashlib.sha256(output.read_bytes()).hexdigest(), includes_model_weights=False)
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--revision', default='HEAD')
    args = parser.parse_args()
    package(args.output, args.revision)
