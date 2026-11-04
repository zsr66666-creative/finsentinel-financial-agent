"""Safe acquisition and reproducible PDF evidence extraction for official filings.

The corpus preserves physical PDF page indices, text offsets, bounding boxes and
SHA-256 hashes. It intentionally does not treat machine-selected eval candidates
as adjudicated golden answers, or a textual risk mention as a confirmed event.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import socket
import time
from urllib.parse import urljoin, urlsplit

import fitz
import requests


ALLOWED_HOSTS = frozenset({"static.cninfo.com.cn", "www.cninfo.com.cn", "www.sse.com.cn", "static.sse.com.cn", "disc.static.szse.cn"})
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA = ROOT / "data"
MAX_PDF_BYTES = 32 * 1024 * 1024


class IngestionError(ValueError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def validate_source_url(url: str, *, resolve: bool = True) -> str:
    """Exact official allowlist, HTTPS-only, no credentials/ports/local addresses."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise IngestionError("invalid source URL") from exc
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or port not in (None, 443)
            or parsed.fragment or "\\" in url or any(ord(c) < 32 for c in url)):
        raise IngestionError("source must be an HTTPS URL on an exact official allowlisted host")
    if resolve:
        try:
            addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise IngestionError("source DNS resolution failed") from exc
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise IngestionError("source resolved to a non-public address")
    return url


class SafeDownloader:
    """Bounded official-source HTTP client; every redirect is revalidated.

    Proxy environment variables are ignored. The fixed host allowlist prevents a
    caller from supplying arbitrary DNS names; DNS results are checked before
    every request. No cookies, credentials or Authorization headers are used.
    """
    def __init__(self, max_bytes=MAX_PDF_BYTES, retries=2):
        self.max_bytes = max_bytes
        self.retries = retries

    def download(self, url: str) -> bytes:
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                current = url
                with requests.Session() as session:
                    session.trust_env = False
                    for hop in range(4):
                        validate_source_url(current)
                        with session.get(current, timeout=(8, 45), stream=True, allow_redirects=False,
                                         headers={"User-Agent": "FinSentinel-research/1.0", "Referer": "https://www.cninfo.com.cn/"}) as response:
                            if response.is_redirect:
                                if hop == 3:
                                    raise IngestionError("too many redirects")
                                current = urljoin(current, response.headers.get("Location", ""))
                                continue
                            response.raise_for_status()
                            content_length = response.headers.get("Content-Length")
                            if content_length and int(content_length) > self.max_bytes:
                                raise IngestionError("PDF exceeds maximum size")
                            payload = bytearray()
                            for chunk in response.iter_content(64 * 1024):
                                payload.extend(chunk)
                                if len(payload) > self.max_bytes:
                                    raise IngestionError("PDF exceeds maximum size")
                            if not payload.startswith(b"%PDF-"):
                                raise IngestionError("response is not a PDF")
                            return bytes(payload)
            except IngestionError:
                raise
            except (requests.RequestException, OSError, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.4 * (attempt + 1))
        raise IngestionError(f"download failed after {self.retries + 1} attempts: {last_error}")


def _atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _extract_page(page, document_id):
    """Offsets refer to this exact text; spans are text blocks in reading order."""
    blocks = page.get_text("blocks", sort=True)
    text_parts, spans = [], []
    offset = 0
    for block in blocks:
        if len(block) > 6 and block[6] != 0:
            continue
        value = block[4]
        if not value.strip():
            continue
        spans.append({"id": f"{document_id}:p{page.number + 1}:s{len(spans) + 1}",
                      "start": offset, "end": offset + len(value), "text": value,
                      "bbox": [round(n, 2) for n in block[:4]]})
        text_parts.append(value)
        offset += len(value) + 1
    text = "\n".join(text_parts)
    units = sorted(set(re.findall(r"(?:单位[：:]?\s*)(人民币元|人民币万元|万元|亿元|千元|元|%)", text)))
    return {"page": page.number + 1, "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "spans": spans, "units": units, "tables": []}


def _selected_pages(document, max_pages=14):
    """Retain all short notices, and compact financial/risk excerpts of reports."""
    if len(document) <= max_pages:
        return list(range(len(document)))
    selected = set(range(min(3, len(document))))
    prioritized = []
    for i in range(3, len(document)):
        text = document[i].get_text()
        score = 0
        if re.search(r"主要会计数据和财务指标|主要财务数据|主要会计数据", text):
            score += 100
        if "经营活动产生的现金流量净额" in text and "营业收入" in text:
            score += 80
        if "合并资产负债表" in text:
            score += 60
        if re.search(r"可能面对的风险|可能面临的风险|风险因素", text):
            score += 40
        if "存货" in text and "应收账款" in text:
            score += 15
        if score:
            prioritized.append((score, i))
    for _, i in sorted(prioritized, key=lambda item: (-item[0], item[1])):
        selected.add(i)
        if len(selected) >= max_pages:
            break
    return sorted(selected)


def _extract_tables(document, pages):
    """Extract geometric PDF tables on summary pages; record failures explicitly."""
    warnings = []
    attempted = 0
    for result in pages:
        text = result["text"]
        if not ("主要会计数据" in text or "主要财务数据" in text or
                ("营业收入" in text and "经营活动产生的现金流量净额" in text)):
            continue
        if attempted >= 3:
            break
        attempted += 1
        page = document[result["page"] - 1]
        try:
            found = page.find_tables()
            for number, table in enumerate(found.tables):
                cells = table.extract()
                if len(cells) > 1:
                    result["tables"].append({"id": f"p{result['page']}:t{number+1}",
                        "method": "pymupdf_geometric", "bbox": [round(n, 2) for n in table.bbox],
                        "rows": cells, "validation_status": "machine_extracted_unreviewed"})
        except Exception as exc:
            warnings.append(f"page {result['page']} table extraction: {type(exc).__name__}: {exc}")
    return warnings


def ingest_pdf(source: Path, metadata: dict, data_dir: Path = DEFAULT_DATA) -> dict:
    """Idempotent per filing/hash; changed bytes create a preserved new version."""
    source, data_dir = Path(source), Path(data_dir)
    payload = source.read_bytes()
    sha = hashlib.sha256(payload).hexdigest()
    filing_id = str(metadata["id"])
    if not re.fullmatch(r"[A-Za-z0-9_:\-]+", filing_id):
        raise IngestionError("invalid filing id")
    existing = sorted((data_dir / "documents").glob(f"{filing_id}.*.json")) if (data_dir / "documents").exists() else []
    prior = [json.loads(p.read_text(encoding="utf-8")) for p in existing]
    for item in prior:
        if item["sha256"] == sha:
            return item
    try:
        document = fitz.open(stream=payload, filetype="pdf")
        if document.is_encrypted or not len(document):
            raise IngestionError("cannot parse encrypted or empty PDF")
        selected = _selected_pages(document)
        pages = [_extract_page(document[i], filing_id) for i in selected]
        table_warnings = _extract_tables(document, pages)
        total_pages = len(document)
        document.close()
    except Exception as exc:
        raise IngestionError(f"PDF parse failed: {type(exc).__name__}: {exc}") from exc
    version = max((item["version"] for item in prior), default=0) + 1
    result = {**metadata, "sha256": sha, "bytes": len(payload), "version": version,
              "supersedes_sha256": max(prior, key=lambda x: x["version"])["sha256"] if prior else None,
              "acquired_at": metadata.get("acquired_at", utc_now()), "parser": f"PyMuPDF {fitz.VersionBind}",
              "total_pages": total_pages, "extracted_page_count": len(pages), "pages": pages,
              "extraction_scope": "complete" if len(pages) == total_pages else "selected_financial_and_risk_pages",
              "metrics": [], "qa": {"text_present": any(p["text"].strip() for p in pages),
                  "offset_integrity": all(p["text"][s["start"]:s["end"]] == s["text"] for p in pages for s in p["spans"]),
                  "tables_reviewed": False, "warnings": table_warnings,
                  "ocr_applied": False, "financial_values_adjudicated": False}}
    _atomic_json(data_dir / "documents" / f"{filing_id}.{sha[:16]}.json", result)
    return result


def official_session():
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"User-Agent": "FinSentinel-research/1.0", "Referer": "https://www.cninfo.com.cn/"})
    return session


def discover_filings(companies, *, start="2024-01-01", end="2025-12-31"):
    """CNINFO exact issuer/category search; 2023/24 annual and 2025 Q3 + event."""
    endpoint = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    validate_source_url(endpoint)
    discovered, errors = [], []
    with official_session() as session:
        response = session.get("https://static.cninfo.com.cn/new/data/szse_stock.json", timeout=30)
        response.raise_for_status()
        stock_list = json.loads(response.content.decode("utf-8"))["stockList"]
        org_ids = {item["code"]: item["orgId"] for item in stock_list}
        for company in companies:
            code = company["code"]
            if code not in org_ids:
                errors.append({"company_code": code, "stage": "discovery", "error": "issuer absent from official SZSE issuer list"})
                continue
            categories = [("category_ndbg_szsh", "annual"), ("category_sjdbg_szsh", "quarterly"),
                          ("category_db_szsh", "guarantee")]
            for category, kind in categories:
                try:
                    response = session.post(endpoint, data={"pageNum": 1, "pageSize": 30,
                        "column": "szse", "tabName": "fulltext", "stock": f"{code},{org_ids[code]}",
                        "searchkey": "", "category": category, "seDate": f"{start}~{end}"}, timeout=30)
                    response.raise_for_status()
                    announcements = json.loads(response.content.decode("utf-8")).get("announcements") or []
                    picked = []
                    for item in announcements:
                        title = re.sub(r"<[^>]*>", "", item["announcementTitle"])
                        if item["secCode"] != code or not item["adjunctUrl"].upper().endswith(".PDF"):
                            continue
                        if kind == "annual":
                            if not re.search(r"202[34]年?年度报告$", title):
                                continue
                            period = re.search(r"202[34]", title).group() + "FY"
                        elif kind == "quarterly":
                            if not re.search(r"2025年?(第三季度报告|三季度报告)$", title):
                                continue
                            period = "2025Q3"
                        else:
                            if "担保" not in title:
                                continue
                            period = None
                        if period and any(p["report_period"] == period for p in picked):
                            continue
                        picked.append({"id": "cninfo-" + item["announcementId"], "company_code": code,
                            "company_name": company["name"], "title": title, "report_type": kind,
                            "report_period": period, "source_url": urljoin("https://static.cninfo.com.cn/", item["adjunctUrl"]),
                            "published_at": datetime.fromtimestamp(item["announcementTime"] / 1000, timezone.utc).date().isoformat(),
                            "announcement_id": item["announcementId"], "discovery_endpoint": endpoint,
                            "source": "CNINFO official listed-company disclosure", "data_mode": "real_public_disclosure"})
                        if kind != "annual" or len(picked) >= 2:
                            break
                    discovered.extend(picked)
                    if not picked:
                        errors.append({"company_code": code, "stage": "discovery", "report_type": kind,
                                       "error": "no matching official filing in search response"})
                except Exception as exc:
                    errors.append({"company_code": code, "stage": "discovery", "report_type": kind,
                                   "error": f"{type(exc).__name__}: {exc}"})
    return discovered, errors


def acquire_and_extract(metadata, data_dir):
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{metadata['id']}.pdf"
    if not raw_path.exists():
        payload = SafeDownloader().download(metadata["source_url"])
        temp = raw_path.with_suffix(".part")
        temp.write_bytes(payload)
        temp.replace(raw_path)
    return ingest_pdf(raw_path, metadata, data_dir)


def assemble_corpus(data_dir):
    """Latest version per source announcement; retain older versions on disk."""
    records = {}
    for path in sorted((data_dir / "documents").glob("*.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        old = records.get(item["id"])
        if not old or item["version"] > old["version"]:
            records[item["id"]] = item
    corpus = sorted(records.values(), key=lambda x: (x["company_code"], x.get("published_at", ""), x["id"]))
    path = data_dir / "corpus.jsonl"
    temp = path.with_suffix(".jsonl.tmp")
    temp.write_text("".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in corpus), encoding="utf-8")
    temp.replace(path)
    return corpus


def build_eval_candidates(corpus, data_dir, limit=40):
    """Evidence-supported candidates, deliberately not adjudicated gold labels."""
    candidates = []
    for filing in corpus:
        if filing["report_type"] == "guarantee":
            continue
        for page in filing["pages"]:
            for span in page["spans"]:
                if ("营业收入" in span["text"] or "经营活动产生的现金流量净额" in span["text"]) and re.search(r"\d[\d,.]*", span["text"]):
                    candidates.append({"id": f"candidate-{len(candidates)+1:03}", "company_code": filing["company_code"],
                        "filing_id": filing["id"], "question": "核对本期营业收入或经营现金流披露，并给出原文及页码。",
                        "report_period": filing["report_period"], "source_url": filing["source_url"],
                        "pdf_sha256": filing["sha256"], "page": page["page"], "span_id": span["id"],
                        "source_text": span["text"], "expected_answer": None,
                        "status": "pending_human_adjudication", "usable_as_scored_gold": False})
                    break
            else:
                continue
            break
        if len(candidates) >= limit:
            break
    _atomic_json(data_dir / "eval_candidates.json", {"purpose": "real-source evaluation annotation queue; not a scored golden set",
                  "status": "pending_human_adjudication", "items": candidates})
    return candidates


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--discover", action="store_true", help="refresh official CNINFO source manifest")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--rebuild", action="store_true", help="reassemble already parsed records without network")
    args = parser.parse_args(argv)
    data_dir = args.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    errors = []
    if args.discover:
        companies = json.loads((data_dir / "companies.json").read_text(encoding="utf-8"))["companies"]
        manifest, errors = discover_filings(companies)
        _atomic_json(data_dir / "source_manifest.json", {"discovered_at": utc_now(), "items": manifest, "errors": errors})
        print(f"Discovered {len(manifest)} official filings; discovery gaps {len(errors)}", flush=True)
    if not args.rebuild:
        source = json.loads((data_dir / "source_manifest.json").read_text(encoding="utf-8"))
        errors = source.get("errors", [])
        items = source["items"][:args.limit] if args.limit else source["items"]
        with ThreadPoolExecutor(max_workers=max(1, min(8, args.workers))) as pool:
            jobs = {pool.submit(acquire_and_extract, item, data_dir): item for item in items}
            for future in as_completed(jobs):
                item = jobs[future]
                try:
                    result = future.result()
                    print(f"OK {item['company_code']} {item['title']} {result['total_pages']} pages", flush=True)
                except Exception as exc:
                    errors.append({"filing_id": item["id"], "source_url": item["source_url"], "stage": "download_parse", "error": f"{type(exc).__name__}: {exc}"})
                    print(f"ERROR {item['id']} {exc}", flush=True)
    corpus = assemble_corpus(data_dir)
    candidates = build_eval_candidates(corpus, data_dir)
    qa = {"generated_at": utc_now(), "data_mode": "real_public_disclosure", "document_count": len(corpus),
          "company_count": len({item["company_code"] for item in corpus}),
          "total_original_pages": sum(item["total_pages"] for item in corpus),
          "extracted_pages": sum(len(item["pages"]) for item in corpus),
          "span_count": sum(len(p["spans"]) for item in corpus for p in item["pages"]),
          "table_count": sum(len(p["tables"]) for item in corpus for p in item["pages"]),
          "all_offsets_valid": all(item["qa"]["offset_integrity"] for item in corpus),
          "metric_count": sum(len(item["metrics"]) for item in corpus),
          "eval_candidate_count": len(candidates), "adjudicated_gold_count": 0,
          "errors": errors, "limitations": ["Selected pages of long reports only; not an exhaustive source corpus.",
              "Geometric tables are machine extracted and require review before financial decisions.",
              "Evaluation candidates are pending human adjudication; no accuracy score is claimed.",
              "Historical disclosures through 2025; no live surveillance or completeness claim."]}
    _atomic_json(data_dir / "ingestion_qa.json", qa)
    print(json.dumps({k: v for k, v in qa.items() if k not in ("errors", "limitations")}, ensure_ascii=False), flush=True)
    return 0 if corpus and qa["all_offsets_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
