"""Ingestion contracts use generated PDFs only as isolated test fixtures."""
import hashlib
import io
import json
from pathlib import Path

import pymupdf as fitz
import pytest

from app.ingestion.pipeline import IngestionError, ingest_pdf, validate_source_url


def fixture_pdf(text="Revenue 100.00"):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), text)
    doc.new_page().insert_text((72, 72), "Cash flow -20.00")
    return doc.tobytes()


def test_page_anchors_are_exact_substrings(tmp_path):
    payload = fixture_pdf()
    source = tmp_path / "source.pdf"
    source.write_bytes(payload)
    result = ingest_pdf(source, {"id": "test-1", "company_code": "002475", "title": "Test"}, tmp_path / "data")
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["total_pages"] == 2
    assert [p["page"] for p in result["pages"]] == [1, 2]
    for page in result["pages"]:
        for span in page["spans"]:
            assert page["text"][span["start"]:span["end"]] == span["text"]
            assert span["id"].startswith("test-1:p")


def test_repeated_ingestion_is_idempotent_and_new_version_is_retained(tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(fixture_pdf())
    meta = {"id": "filing-1", "company_code": "002475", "title": "Test"}
    first = ingest_pdf(source, meta, tmp_path / "data")
    second = ingest_pdf(source, meta, tmp_path / "data")
    assert first == second
    assert len(list((tmp_path / "data" / "documents").glob("*.json"))) == 1
    source.write_bytes(fixture_pdf("Revenue 120.00"))
    third = ingest_pdf(source, meta, tmp_path / "data")
    assert third["version"] == 2
    assert third["supersedes_sha256"] == first["sha256"]
    assert len(list((tmp_path / "data" / "documents").glob("*.json"))) == 2


def test_malformed_pdf_is_explicit_and_does_not_create_corpus(tmp_path):
    source = tmp_path / "bad.pdf"
    source.write_bytes(b"%PDF-1.7 broken data")
    with pytest.raises(IngestionError, match="parse"):
        ingest_pdf(source, {"id": "bad"}, tmp_path / "data")
    assert not (tmp_path / "data" / "corpus.jsonl").exists()


@pytest.mark.parametrize("url", [
    "http://static.cninfo.com.cn/a.pdf", "https://static.cninfo.com.cn.evil.test/a.pdf",
    "https://127.0.0.1/a.pdf", "https://169.254.169.254/latest/meta-data",
    "https://user:password@static.cninfo.com.cn/a.pdf", "https://static.cninfo.com.cn:444/a.pdf",
    "file:///C:/Windows/win.ini", "https://static.cninfo.com.cn/a.pdf#fragment",
])
def test_downloader_rejects_unapproved_sources_without_network(url):
    with pytest.raises(IngestionError):
        validate_source_url(url, resolve=False)


def test_downloader_accepts_exact_official_host():
    assert validate_source_url("https://static.cninfo.com.cn/finalpage/2025-01-01/1.PDF", resolve=False)

