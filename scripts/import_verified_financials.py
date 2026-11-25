"""Import manually approved metrics after binding them to acquired official PDFs."""
import argparse
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import fitz
from sqlalchemy import create_engine, text

from app.corpus import load_corpus
from app.store import Store


def _normalize(value):
    return re.sub(r'\s+', '', value)


def _read_records(path):
    records = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    if len(records) != 2 or {row.get('company_code') for row in records} != {'000157'}:
        raise ValueError('expected exactly the two approved 000157 filings')
    if {row.get('report_period') for row in records} != {'2023FY', '2024FY'}:
        raise ValueError('expected 2023FY and 2024FY filings')
    keys = set()
    for row in records:
        identity = hashlib.sha256(json.dumps([row['company_code'], row['report_period'], row['report_type'], row['sha256']]).encode()).hexdigest()
        if row.get('id') != identity or row.get('report_type') != 'annual':
            raise ValueError('filing identity mismatch')
        if not re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', '')):
            raise ValueError('invalid filing SHA256')
        if not row.get('source_url', '').startswith('https://static.cninfo.com.cn/finalpage/'):
            raise ValueError('unapproved filing source')
        if len(row.get('metrics', [])) != 2:
            raise ValueError('each filing must contain exactly two approved metrics')
        for metric in row['metrics']:
            key = (metric.get('metric'), metric.get('period'))
            if key in keys:
                raise ValueError('duplicate financial metric period')
            keys.add(key)
            if (metric.get('extraction_status') != 'human_verified'
                    or metric.get('statement_scope') != 'consolidated'
                    or metric.get('unit') != 'CNY'
                    or metric.get('period') != row['report_period']
                    or metric.get('page', 0) < 1
                    or len(metric.get('source_ids', [])) != 1):
                raise ValueError('financial metric contract mismatch')
            try:
                value = Decimal(metric['value'])
            except (InvalidOperation, TypeError):
                raise ValueError('invalid financial metric value') from None
            if not value.is_finite() or value <= 0 or value > Decimal('100000000000000000000'):
                raise ValueError('financial metric value outside approved range')
            if not metric.get('excerpt') or metric['excerpt'] not in '\n'.join(
                    span.get('text', '') for page in row['pages'] for span in page.get('spans', [])):
                raise ValueError('metric excerpt does not match its page evidence')
    if keys != {('net_profit', '2023FY'), ('operating_cash_flow', '2023FY'),
                ('net_profit', '2024FY'), ('operating_cash_flow', '2024FY')}:
        raise ValueError('approved metric set mismatch')
    return records


def _verify_artifacts(engine, records, artifact_root):
    root = Path(artifact_root).resolve(strict=True)
    with engine.connect() as connection:
        for record in records:
            artifact = connection.execute(text('''SELECT id, sha256, company_code, report_period, report_type
                FROM ingestion_artifacts WHERE id=:id'''), {'id': record['id']}).mappings().one_or_none()
            if not artifact or any(artifact[key] != record[key] for key in ('id', 'sha256', 'company_code', 'report_period', 'report_type')):
                raise ValueError(f"ingestion artifact identity mismatch: {record['report_period']}")
            pdf = (root / 'blobs' / f"{record['sha256']}.pdf").resolve()
            if not pdf.is_relative_to(root / 'blobs'):
                raise ValueError('PDF blob escapes ingestion root')
            if not pdf.is_file():
                raise ValueError(f"PDF blob missing: {record['report_period']}")
            if hashlib.sha256(pdf.read_bytes()).hexdigest() != record['sha256']:
                raise ValueError('PDF checksum mismatch')
            with fitz.open(pdf) as document:
                for metric in record['metrics']:
                    page_number = metric['page']
                    if page_number > len(document):
                        raise ValueError('physical page is outside PDF')
                    source_text = document[page_number - 1].get_text()
                    excerpt = _normalize(metric['excerpt'])
                    number = f"{Decimal(metric['value']):,.2f}"
                    if number not in source_text or excerpt not in _normalize(source_text):
                        raise ValueError(f"cited PDF page does not contain verified metric: {record['report_period']} {metric['metric']}")
    return root


def import_verified_financials(engine, corpus_path, artifact_root, check_only=False):
    records = _read_records(corpus_path)
    _verify_artifacts(engine, records, artifact_root)
    store = Store(str(engine.url))
    try:
        planned_ids = set()
        for record in records:
            for index, metric in enumerate(record['metrics']):
                planned_ids.add(f"{record['id']}-metric-{metric['metric']}-{index}")
        existing = store.all('financial_metrics')
        for metric in existing:
            if (metric.get('company_id') == '000157' and metric.get('period') in ('2023FY', '2024FY')
                    and metric.get('metric') in ('net_profit', 'operating_cash_flow')
                    and metric.get('id') not in planned_ids):
                raise ValueError('conflicting existing metric for an approved company/period')
        for record in records:
            for page in record['pages']:
                for index, span in enumerate(page['spans']):
                    evidence_id = f"{record['id']}-p{page['page']}-s{index}"
                    if evidence_id not in {source for metric in record['metrics'] for source in metric['source_ids']}:
                        raise ValueError('page span is not bound to an approved metric evidence id')
        before = {metric['id'] for metric in existing}
        if check_only:
            return {'documents': len(records), 'metrics': len(planned_ids), 'inserted': 0,
                    'existing': len(before & planned_ids), 'check_only': True}
        result = load_corpus(store, corpus_path)
        after = {metric['id'] for metric in store.all('financial_metrics')}
        return {'documents': result['documents'], 'metrics': sum(len(row['metrics']) for row in records),
                'inserted': len((after - before) & planned_ids),
                'existing': len(before & planned_ids)}
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database-url', required=True)
    parser.add_argument('--corpus', required=True)
    parser.add_argument('--artifact-root', required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    engine = create_engine(args.database_url)
    try:
        print(json.dumps(import_verified_financials(engine, args.corpus, args.artifact_root, args.check_only), ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
