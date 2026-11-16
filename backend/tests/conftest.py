"""Test bootstrap that works from the repository root or backend directory."""

from pathlib import Path
import sys
from uuid import uuid4
import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
# Integration helpers live at repository level; CI runs from backend/.
for import_root in (BACKEND_ROOT, BACKEND_ROOT.parent):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


@pytest.fixture
def tmp_path(request):
    """Workspace-local tmp_path for hosts whose global pytest temp is ACL-locked."""
    root = BACKEND_ROOT.parent / '.test-tmp-week13' / f'{request.node.name}-{uuid4().hex}'
    root.mkdir(parents=True, exist_ok=True)
    return root

