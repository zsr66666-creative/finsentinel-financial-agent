"""Build a private, checksum-verified Task 8 ECS archive including the pinned model."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile


MODEL_REVISION = '7999e1d3359715c523056ef9478215996d62a620'
MODEL_SHA256 = '6e644f914603e965204e410e7b74c7c60e070489292a2ac34eb0c8e889a4940b'


def load_model_artifacts(model_dir):
    model_root = Path(model_dir).resolve()
    reference = json.loads((model_root / 'reference.json').read_text(encoding='utf-8'))
    assessment = json.loads((model_root / 'assessment.json').read_text(encoding='utf-8'))
    runtime_manifest = json.loads((model_root / 'manifest.json').read_text(encoding='utf-8'))
    if reference.get('revision') != MODEL_REVISION or assessment.get('revision') != MODEL_REVISION:
        raise ValueError('Task 8 model revision mismatch')
    if not assessment.get('parity_passed') or assessment.get('imported_torch'):
        raise ValueError('Task 8 model assessment did not pass CPU parity without torch')
    if runtime_manifest.get('model') != f'BAAI/bge-small-zh-v1.5@{MODEL_REVISION}':
        raise ValueError('Task 8 runtime model manifest mismatch')
    if runtime_manifest.get('prefix') != reference.get('prefix'):
        raise ValueError('Task 8 model prefix mismatch')

    artifacts = {}
    for name in ('model.onnx', 'tokenizer.json'):
        data = (model_root / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != runtime_manifest.get('files', {}).get(name):
            raise ValueError('Task 8 model manifest checksum mismatch: ' + name)
        artifacts['model/' + name] = data
    if hashlib.sha256(artifacts['model/model.onnx']).hexdigest() != MODEL_SHA256:
        raise ValueError('Task 8 ONNX model SHA-256 mismatch')
    for name in ('tokenizer_config.json', 'reference.json', 'manifest.json'):
        artifacts['model/' + name] = (model_root / name).read_bytes()
    return artifacts


def package(output, model_dir, revision='HEAD'):
    root = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(
        ['git', 'rev-parse', revision + '^{commit}'], cwd=root, text=True
    ).strip()
    paths = ['backend', 'frontend', 'scripts', 'deploy/ecs/install-task8-offline.sh']
    exported = subprocess.check_output(
        ['git', 'archive', '--format=tar', commit, *paths], cwd=root
    )
    files = {}
    with tarfile.open(fileobj=io.BytesIO(exported), mode='r:') as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            path = PurePosixPath(member.name)
            if not member.isfile() or path.is_absolute() or '..' in path.parts:
                raise ValueError('unsafe git archive entry')
            data = archive.extractfile(member).read()
            if member.name.endswith('.sh') and b'\r' in data:
                raise ValueError('Shell scripts must retain LF: ' + member.name)
            files[member.name] = data

    files.update(load_model_artifacts(model_dir))
    files['model/LICENSE.txt'] = (
        b'Model: BAAI/bge-small-zh-v1.5\n'
        b'Revision: 7999e1d3359715c523056ef9478215996d62a620\n'
        b'License: MIT\n'
        b'Upstream: https://huggingface.co/BAAI/bge-small-zh-v1.5\n'
    )
    files['SOURCE_REVISION'] = (commit + '\n').encode()
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    files['PACKAGE_FILES.json'] = (json.dumps(manifest, indent=2) + '\n').encode()

    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('wb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w|') as archive:
            for name, data in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o755 if name.endswith('.sh') else 0o644
                archive.addfile(info, io.BytesIO(data))

    report = {
        'path': str(output),
        'source_revision': commit,
        'model_revision': MODEL_REVISION,
        'model_sha256': MODEL_SHA256,
        'files': len(files),
        'bytes': output.stat().st_size,
        'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--model-dir', required=True)
    parser.add_argument('--revision', default='HEAD')
    args = parser.parse_args()
    package(args.output, args.model_dir, args.revision)
