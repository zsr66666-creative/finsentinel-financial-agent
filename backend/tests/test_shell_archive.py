"""Release scripts must stay executable by Linux bash after git archive."""
import io
from pathlib import Path
import subprocess
import tarfile


def test_git_archive_keeps_shell_scripts_lf():
    repo = Path(__file__).resolve().parents[2]
    raw = subprocess.check_output(['git', 'archive', '--format=tar', '--worktree-attributes', 'HEAD', 'deploy/ecs/install-task8-offline.sh'], cwd=repo)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as bundle:
        data = bundle.extractfile('deploy/ecs/install-task8-offline.sh').read()
    assert b'\r' not in data, 'CRLF breaks bash conditionals and heredocs'
    assert data.startswith(b'#!/usr/bin/env bash\n')
