"""Read-only financial comparisons bound to pinned official report bytes.

Source verification does not imply independent human adjudication. Never use
retrieval candidates or seeded demo metrics as numerical evidence here.
"""
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import json
from pathlib import Path
import re

from sqlalchemy import inspect, text

CONTRACT_PATH = Path(__file__).with_name('data') / 'task11-financial-contracts.json'
DEFAULT_ARTIFACT_ROOT = '/var/lib/finsentinel/ingestion'
AMOUNT = re.compile(r'-?\d{1,18}\.\d{2}\Z')


def compact(value):
    return ''.join(value.split())


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def calculate_change(current, previous):
    if any(not isinstance(value, str) or not AMOUNT.fullmatch(value) for value in (current, previous)):
        raise ValueError('finite fixed-point monetary strings required')
    with localcontext() as ctx:
        ctx.prec = 40
        current, previous = Decimal(current), Decimal(previous)
        difference = current - previous
        percent = None if not previous else format((difference / abs(previous) * 100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP), '.2f')
        return dict(difference=format(difference, '.2f'), change_percent=percent,
                    change_percent_reason='zero_comparison_base' if not previous else None,
                    direction='increase' if difference > 0 else 'decrease' if difference < 0 else 'unchanged')


def load_contracts():
    manifest = json.loads(CONTRACT_PATH.read_text(encoding='utf-8'))
    if manifest['version'] != 'task11-financial-contract-v1':
        raise ValueError('unknown financial source contract')
    return manifest['reports']


def rejected_metric(metric, reason):
    return dict(metric=metric['metric'], label=metric['label'], status='needs_review',
                review_status='pending_human', reason=reason, evidence=[])


def _statement_semantics(report, metric):
    if report['report_period'] != '2024FY' or report['company_code'] not in ('002555', '002230'):
        raise ValueError('unsupported report period')
    label, title = {
        'revenue': ('营业收入', '3、合并利润表'),
        'receivables': ('应收账款', '1、合并资产负债表'),
        'operating_cash_flow': ('经营活动产生的现金流量净额', '5、合并现金流量表'),
    }[metric['metric']]
    meta = dict(label=label, unit='CNY', statement_scope='consolidated')
    if metric['metric'] != 'receivables':
        meta.update(period_kind='flow', current_period='2024-01-01/2024-12-31',
                    previous_period='2023-01-01/2023-12-31', current_column='2024 年度', previous_column='2023 年度')
        columns = title + '单位：元项目2024年度2023年度'
    else:
        explicit_dates = report['company_code'] == '002230'
        meta.update(period_kind='balance', current_period='2024-12-31',
                    previous_period='2024-01-01' if explicit_dates else 'opening_balance_2024',
                    current_column='2024 年12 月31 日' if explicit_dates else '期末余额',
                    previous_column='2024 年1 月1 日' if explicit_dates else '期初余额')
        columns = '项目2024年12月31日2024年1月1日' if explicit_dates else '项目期末余额期初余额'
    return meta, title, columns


def verify_metric(report, metric, pages):
    """Check immutable page/row/title/unit/column proofs before exposing amounts."""
    rejected = rejected_metric(metric, 'source_contract_mismatch')
    try:
        anchors = metric['evidence']
        roles = {a['role']: a for a in anchors}
        if not {'row', 'statement', 'unit', 'columns'} <= roles.keys():
            return rejected
        meta, title, columns = _statement_semantics(report, metric)
        if any(metric[key] != value for key, value in meta.items()):
            return rejected
        if len(roles) != len(anchors) or compact(roles['statement']['text']) != title or compact(roles['unit']['text']) != '单位：元' or compact(roles['columns']['text']) != columns:
            return rejected
        if roles['columns']['page'] != roles['statement']['page'] or roles['unit']['page'] != roles['statement']['page']:
            return rejected
        if metric['metric'] == 'receivables' and ('balance_date' not in roles or compact(roles['balance_date']['text']) != '2024年12月31日' or roles['balance_date']['page'] != roles['statement']['page']):
            return rejected
        title_page, row_page = roles['statement']['page'], roles['row']['page']
        if not title_page <= row_page <= title_page + 1:
            return rejected
        if metric['statement_scope'] != 'consolidated' or metric['unit'] != 'CNY':
            return rejected
        # The row itself must contain exactly the label and two approved amounts.
        row_label = '其中：营业收入' if metric['metric'] == 'revenue' else metric['label']
        row = compact(row_label + format(Decimal(metric['current_value']), ',.2f') + format(Decimal(metric['previous_value']), ',.2f'))
        if compact(roles['row']['text']) != row:
            return rejected
        if title_page == row_page and compact(pages[row_page]).index(compact(roles['statement']['text'])) >= compact(pages[row_page]).index(row):
            return rejected
        evidence = []
        for anchor in anchors:
            page = compact(pages[anchor['page']])
            excerpt = compact(anchor['text'])
            if digest(page) != anchor['page_text_sha256'] or digest(excerpt) != anchor['text_sha256'] or excerpt not in page:
                return rejected
            start = page.index(excerpt)
            evidence.append(dict(**anchor, evidence_id=f"task11-{report['document_id']}-p{anchor['page']}-{anchor['role']}",
                                 normalized_start=start, normalized_end=start+len(excerpt)))
        return dict(**{k: metric[k] for k in ('metric','label','statement_scope','unit','period_kind','current_period','previous_period','current_column','previous_column','current_value','previous_value')},
                    **calculate_change(metric['current_value'], metric['previous_value']), status='supported',
                    review_status='pending_human', source_validation='pdf_hash_and_statement_contract',
                    company_code=report['company_code'], report_period=report['report_period'],
                    document_id=report['document_id'], source_sha256=report['sha256'], source_url=report['source_url'],
                    extraction_method='pymupdf_text_whitespace_normalized', evidence=evidence)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return rejected


def _source_pages(engine, report, artifact_root):
    if not inspect(engine).has_table('ingestion_artifacts'):
        return None, 'official_artifact_unavailable'
    with engine.connect() as conn:
        if engine.dialect.name == 'postgresql':
            conn.execute(text('SET TRANSACTION READ ONLY'))
        rows = conn.execute(text('SELECT id,sha256,company_code,report_period,report_type FROM ingestion_artifacts WHERE id=:id'),
                            {'id': report['document_id']}).mappings().all()
    if len(rows) != 1 or any(rows[0][key] != report[key] for key in ('sha256','company_code','report_period','report_type')):
        return None, 'official_artifact_unavailable'
    try:
        root = Path(artifact_root).resolve(strict=True)
        path = (root/'blobs'/(report['sha256']+'.pdf')).resolve(strict=True)
        if not path.is_relative_to(root/'blobs') or path.stat().st_size > 32*1024*1024:
            return None, 'source_pdf_unavailable'
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != report['sha256']:
            return None, 'source_pdf_hash_mismatch'
        import fitz
        with fitz.open(stream=payload, filetype='pdf') as document:
            if document.is_encrypted or len(document) != report['total_pages']:
                return None, 'source_pdf_contract_mismatch'
            numbers = {e['page'] for metric in report['metrics'] for e in metric['evidence']}
            pages = {page: document[page-1].get_text() for page in numbers}
        return pages, None
    except (OSError, ValueError, RuntimeError):
        return None, 'source_pdf_unavailable'


def company_comparisons(engine, company_code, period='2024FY', statement_scope='consolidated', artifact_root=DEFAULT_ARTIFACT_ROOT):
    base = dict(company_code=company_code, period=period, statement_scope=statement_scope,
                data_mode='source_verified_financial_contract', review_status='pending_human',
                percentage_formula='(current - previous) / abs(previous) * 100',
                limitations=['six_fixed_metric_contracts_only', 'source_validation_is_not_human_adjudication',
                             'opening_balance_labels_preserved', 'numeric_change_is_not_a_risk_conclusion'])
    report = next((r for r in load_contracts() if r['company_code'] == company_code), None)
    if report is None or period != '2024FY' or statement_scope != 'consolidated':
        return dict(**base, status='needs_review', reason='unsupported_company_period_or_scope', items=[], total=0)
    pages, reason = _source_pages(engine, report, artifact_root)
    items = [rejected_metric(metric, reason) if pages is None else verify_metric(report, metric, pages) for metric in report['metrics']]
    return dict(**base, status='supported' if all(i['status']=='supported' for i in items) else 'needs_review',
                items=items, total=len(items))
