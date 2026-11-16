"""Package committed saved research report sources, no model/PDF/secrets/builds."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile


def package(output, revision='HEAD'):
    root=Path(__file__).resolve().parents[1]
    commit=subprocess.check_output(['git','rev-parse',revision+'^{commit}'],cwd=root,text=True).strip()
    paths=['backend','frontend','scripts','deploy/ecs/install-saved-reports-offline.sh','docs/saved-reports.md',
        'docs/superpowers/specs/2026-11-16-saved-reports-design.md']
    raw=subprocess.check_output(['git','archive','--format=tar',commit,*paths],cwd=root)
    files={}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for entry in archive.getmembers():
            if entry.isdir():continue
            path=PurePosixPath(entry.name)
            if not entry.isfile() or path.is_absolute() or '..' in path.parts:raise ValueError('unsafe archive')
            content=archive.extractfile(entry).read()
            if entry.name.endswith('.sh') and b'\r' in content:raise ValueError('Shell script must be LF: '+entry.name)
            files[entry.name]=content
    files['PACKAGE_FILES.json']=(json.dumps({name:hashlib.sha256(content).hexdigest() for name,content in sorted(files.items())},indent=2)+'\n').encode()
    files['SOURCE_REVISION']=(commit+'\n').encode()
    output=Path(output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('wb') as stream,gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as compressed:
        with tarfile.open(fileobj=compressed,mode='w|') as archive:
            for name,content in sorted(files.items()):
                info=tarfile.TarInfo(name);info.size=len(content);info.mode=0o755 if name.endswith('.sh') else 0o644
                archive.addfile(info,io.BytesIO(content))
    with tarfile.open(output,'r:gz') as archive:
        unpacked={m.name:archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}
    assert unpacked==files
    assert not any('node_modules' in n or '.next/' in n or n.endswith(('.env','.pdf','.PDF','.db','.onnx','.tsbuildinfo')) for n in files)
    report=dict(path=str(output),source_revision=commit,files=len(files),bytes=output.stat().st_size,sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    print(json.dumps(report,indent=2));return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--revision',default='HEAD');args=parser.parse_args()
    package(args.output,args.revision)
