import hashlib
import json
from decimal import Decimal

import fitz
import pytest
from sqlalchemy import create_engine, text
from pathlib import Path

from scripts.import_verified_financials import import_verified_financials


def source_fixture(tmp_path):
    root = tmp_path / 'ingestion'
    (root / 'blobs').mkdir(parents=True)
    corpus = tmp_path / 'verified.jsonl'
    records = []
    for year, period, profit, cash in [(2023, '2023FY', '3506011590.67', '2712551743.37'),
                                       (2024, '2024FY', '3520377530.14', '2142055023.05')]:
        profit_excerpt = f'STATEMENT net profit {Decimal(profit):,.2f} {"2,306,047,166.93" if year == 2023 else "3,506,011,590.67"}'
        cash_excerpt = f'STATEMENT operating cash flow {Decimal(cash):,.2f} {"2,424,632,272.28" if year == 2023 else "2,712,551,743.37"}'
        pdf_doc = fitz.open()
        pdf_doc.new_page().insert_text((72, 72), 'cover')
        pdf_doc.new_page().insert_text((72, 72), profit_excerpt)
        pdf_doc.new_page().insert_text((72, 72), cash_excerpt)
        pdf = pdf_doc.tobytes()
        pdf_doc.close()
        digest = hashlib.sha256(pdf).hexdigest()
        (root / 'blobs' / f'{digest}.pdf').write_bytes(pdf)
        identity = hashlib.sha256(json.dumps(['000157', period, 'annual', digest]).encode()).hexdigest()
        records.append({
            'id': identity, 'company_code': '000157', 'report_period': period,
            'report_type': 'annual', 'sha256': digest,
            'source_url': f'https://static.cninfo.com.cn/finalpage/{year}-03-25/test.pdf',
            'pages': [
                {'page': 2, 'spans': [{'start': 0, 'end': len(profit_excerpt), 'text': profit_excerpt}]},
                {'page': 3, 'spans': [{'start': 0, 'end': len(cash_excerpt), 'text': cash_excerpt}]},
            ],
            'metrics': [
                {'metric': 'net_profit', 'value': profit, 'period': period, 'unit': 'CNY',
                 'statement_scope': 'consolidated', 'page': 2, 'excerpt': profit_excerpt,
                 'extraction_status': 'human_verified', 'source_ids': [f'{identity}-p2-s0']},
                {'metric': 'operating_cash_flow', 'value': cash, 'period': period, 'unit': 'CNY',
                 'statement_scope': 'consolidated', 'page': 3, 'excerpt': cash_excerpt,
                 'extraction_status': 'human_verified', 'source_ids': [f'{identity}-p3-s0']},
            ],
        })
    corpus.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
    return root, corpus, records


def artifact_database(tmp_path, record):
    engine = create_engine(f'sqlite:///{tmp_path / "artifacts.db"}')
    with engine.begin() as conn:
        conn.execute(text('''CREATE TABLE ingestion_artifacts (
            id TEXT PRIMARY KEY, sha256 TEXT, company_code TEXT,
            report_period TEXT, report_type TEXT)'''))
        conn.execute(text('INSERT INTO ingestion_artifacts VALUES (:id,:sha,:code,:period,:kind)'), {
            'id': record['id'], 'sha': record['sha256'], 'code': record['company_code'],
            'period': record['report_period'], 'kind': record['report_type']})
    return engine


def test_verified_import_checks_pdf_identity_and_is_idempotent(tmp_path):
    root, corpus, records = source_fixture(tmp_path)
    engine = artifact_database(tmp_path, records[0])
    with engine.begin() as conn:
        row = records[1]
        conn.execute(text('INSERT INTO ingestion_artifacts VALUES (:id,:sha,:code,:period,:kind)'), {
            'id':row['id'],'sha':row['sha256'],'code':row['company_code'],
            'period':row['report_period'],'kind':row['report_type']})
    try:
        result = import_verified_financials(engine, corpus, root)
        assert result == {'documents': 2, 'metrics': 4, 'inserted': 4, 'existing': 0}
        again = import_verified_financials(engine, corpus, root)
        assert again == {'documents': 2, 'metrics': 4, 'inserted': 0, 'existing': 4}
    finally:
        engine.dispose()


def test_verified_import_rejects_wrong_pdf_hash_before_writing(tmp_path):
    root, corpus, records = source_fixture(tmp_path)
    pdf = root / 'blobs' / f"{records[0]['sha256']}.pdf"
    pdf.write_bytes(pdf.read_bytes() + b'corrupt')
    engine = artifact_database(tmp_path, records[0])
    with engine.begin() as conn:
        row=records[1]
        conn.execute(text('INSERT INTO ingestion_artifacts VALUES (:id,:sha,:code,:period,:kind)'), {
            'id':row['id'],'sha':row['sha256'],'code':row['company_code'],
            'period':row['report_period'],'kind':row['report_type']})
    try:
        with pytest.raises(ValueError, match='PDF checksum mismatch'):
            import_verified_financials(engine, corpus, root)
    finally:
        engine.dispose()


def test_verified_import_rejects_value_missing_from_cited_physical_page(tmp_path):
    root, corpus, records = source_fixture(tmp_path)
    records[0]['metrics'][0]['value'] = '999'
    corpus.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
    engine = artifact_database(tmp_path, records[0])
    with engine.begin() as conn:
        row=records[1]
        conn.execute(text('INSERT INTO ingestion_artifacts VALUES (:id,:sha,:code,:period,:kind)'), {
            'id':row['id'],'sha':row['sha256'],'code':row['company_code'],
            'period':row['report_period'],'kind':row['report_type']})
    try:
        with pytest.raises(ValueError, match='cited PDF page does not contain'):
            import_verified_financials(engine, corpus, root)
    finally:
        engine.dispose()


def test_check_only_verifies_sources_without_writing_metrics(tmp_path):
    root, corpus, records = source_fixture(tmp_path)
    engine = artifact_database(tmp_path, records[0])
    with engine.begin() as conn:
        row = records[1]
        conn.execute(text('INSERT INTO ingestion_artifacts VALUES (:id,:sha,:code,:period,:kind)'), {
            'id': row['id'], 'sha': row['sha256'], 'code': row['company_code'],
            'period': row['report_period'], 'kind': row['report_type']})
    try:
        result = import_verified_financials(engine, corpus, root, check_only=True)
        assert result['check_only'] is True
        assert result['metrics'] == 4
        assert engine.connect().execute(text('SELECT count(*) FROM financial_metrics')).scalar_one() == 0
    finally:
        engine.dispose()


def test_offline_installer_keeps_encoder_out_of_restart_path_and_has_acceptance_checks():
    root = Path(__file__).resolve().parents[2]
    script = (root / 'deploy/ecs/install-financial-analysis-offline.sh').read_text(encoding='utf-8')
    assert 'systemctl restart finsentinel-query-encoder' not in script
    assert '--check-only' in script
    assert 'PASS post-import API' in script
    assert 'PASS nginx company 000157' in script
    assert 'Environment=DATA_MODE=real_corpus' in script
