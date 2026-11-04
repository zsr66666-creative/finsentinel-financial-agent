"""Compatibility shim for legacy ``import fitz`` callers.

PyMuPDF's supported import name is ``pymupdf``.  Keeping this tiny adapter
allows older ingestion scripts and tests to continue importing ``fitz`` while
using the same installed PyMuPDF implementation.
"""

from pymupdf import *  # noqa: F401,F403
from pymupdf import VersionBind

