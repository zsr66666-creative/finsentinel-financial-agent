# Data contract

This is the v0.1 data contract for the first real metric flow. It supports four tables before the project grows into the full research workbench.

## Entity relationships

```text
companies 1 ─── * documents 1 ─── * evidence_spans
companies 1 ─── * financial_metrics * ─── 1 documents
```

`financial_metrics` stores reported or derived values. `evidence_spans` stores the exact page or text location that supports a value. A derived metric must record its formula and every input evidence ID.

## companies

| Field | Type | Required | Rule |
|---|---|---:|---|
| `id` | string | yes | Stable internal ID, e.g. `cn-002475` |
| `ticker` | string | yes | Six digit security code; unique with `exchange` |
| `name` | string | yes | Official company name |
| `exchange` | enum | yes | `SZ`, `SH`, or `BJ` |
| `industry` | string | yes | Initial value: `消费电子/电子制造` |
| `created_at` | datetime | yes | UTC timestamp |

## documents

| Field | Type | Required | Rule |
|---|---|---:|---|
| `id` | string | yes | Stable document ID |
| `company_id` | FK | yes | References `companies.id` |
| `title` | string | yes | Original report or announcement title |
| `document_type` | enum | yes | `annual_report`, `half_year_report`, `quarterly_report`, `announcement` |
| `report_period` | string | yes | `2026H1`, `2024FY`; accounting period |
| `published_at` | date | no | Official disclosure date |
| `source_url` | URL/null | no | Exact official URL; null when unverified |
| `accessed_at` | datetime | yes | Retrieval or recording time |
| `sha256` | string | yes | 64 lowercase hex characters |
| `file_size_bytes` | integer | yes | Non-negative original file size |
| `page_count` | integer | yes | Positive PDF page count |
| `extraction_method` | enum | yes | `manual`, `pymupdf`, `ocr`, `table_parser` |
| `quality_status` | enum | yes | `page_verified`, `needs_review`, `parse_failed` |

The unique document key is `(company_id, sha256)`. Re-importing the same file must not create duplicate rows. A changed file gets a new document version and keeps the old record.

## financial_metrics

| Field | Type | Required | Rule |
|---|---|---:|---|
| `id` | string | yes | Stable metric record ID |
| `company_id` | FK | yes | References `companies.id` |
| `document_id` | FK | yes | Supporting document |
| `metric` | enum/string | yes | v0.1: `revenue`, `net_profit_attributable`, `inventory` |
| `value` | Decimal/Numeric | no | Exact source precision; `NULL` means unavailable |
| `currency` | enum | yes | v0.1: `CNY` |
| `unit` | enum | yes | `元`, `千元`, `百万元`, or explicit source unit |
| `period` | string | yes | Accounting period or balance-sheet date |
| `statement_scope` | enum | yes | `consolidated` or `parent_company` |
| `source_page` | integer | no | Physical PDF page |
| `formula` | string/null | no | Null for reported; required for derived values |
| `source_evidence_ids` | list | yes | Evidence IDs supporting the value |
| `quality_status` | enum | yes | `page_verified`, `needs_review`, `missing`, `unit_check_required` |

Never silently convert `千元` to `元`. Preserve original value/unit and record any conversion rule. Missing values remain `NULL` with a reason; zero is a real number. `net_profit_attributable` means “归属于上市公司股东的净利润” and cannot be mixed with other profit definitions.

## evidence_spans

| Field | Type | Required | Rule |
|---|---|---:|---|
| `id` | string | yes | Stable evidence ID |
| `document_id` | FK | yes | References `documents.id` |
| `page_no` | integer | yes | One-based physical PDF page |
| `text` | text | yes | Exact or minimally normalized excerpt |
| `source_url` | URL/null | no | Verified official URL when available |
| `start_offset` | integer/null | no | Offset in page text |
| `end_offset` | integer/null | no | Greater than or equal to start |
| `extraction_method` | enum | yes | Extraction method used |

## Time and comparison rules

- `report_period` describes the accounting period; `published_at` describes public disclosure; `accessed_at` describes retrieval.
- Historical analysis uses only documents with `published_at <= as_of`.
- Annual, half-year and quarterly periods cannot be compared as equal lengths.
- `2026H1` is not `2026FY`.
- Cross-company comparisons require the same period, currency, unit, statement scope and documented comparability.

## v0.1 record

`data/examples/first-company-metrics.json` records three page-verified values from the locally supplied 2026 half-year report. Its official `source_url` remains null until verified from the issuer or CNINFO.
