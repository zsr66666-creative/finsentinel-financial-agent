"""Interpreter compatibility for legacy PyMuPDF imports.

When pytest starts from ``backend/``, Python loads this module before test
collection. It provides the historical ``fitz`` name without installing the
unrelated PyPI package also called ``fitz``.
"""

import sys

try:
    import pymupdf
except ImportError:
    pass
else:
    sys.modules.setdefault("fitz", pymupdf)

