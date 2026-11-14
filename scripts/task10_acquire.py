"""Enqueue the two approved official reports; resident worker owns acquisition."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from sqlalchemy import create_engine, select

from app.ingestion.source_policy import check_url
from app.ingestion.task_queue import enqueue_task, tasks
from app.research_companies import RESEARCH_COMPANIES


def load_reports():
    path = Path(__file__).resolve().parents[1] / 'data/manifests/task10-official-reports.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    reports = manifest['reports']
    if manifest['version'] != 'task10-2024fy-v1' or len(reports) != 2 or {r['company_code'] for r in reports} != {'002555', '002230'}:
        raise ValueError('unexpected approved report set')
    for report in reports:
        identity = RESEARCH_COMPANIES[report['company_code']]
        if (report['company_name'] != identity['company_name'] or report['industry'] != identity['industry']
                or report['report_period'] != '2024FY' or report['report_type'] != 'annual'
                or len(report['sha256']) != 64 or any(c not in '0123456789abcdef' for c in report['sha256'])):
            raise ValueError('invalid approved report identity')
        check_url(report['source_url'])
        expected = hashlib.sha256(json.dumps([report[k] for k in ('company_code', 'report_period', 'report_type', 'sha256')]).encode()).hexdigest()
        if report['document_id'] != expected:
            raise ValueError('invalid approved document identity')
    return reports


def enqueue_reports(engine, reports):
    ids = []
    for report in reports:
        request = {key: report[key] for key in ('source_url', 'company_code', 'report_period', 'report_type')}
        row = enqueue_task(engine, request, 'task10-2024fy-v1-' + report['company_code'])
        ids.append(row['id'])
    return ids


def completed_reports(engine, reports, task_ids):
    with engine.connect() as conn:
        rows = {r['id']: r for r in conn.execute(select(tasks).where(tasks.c.id.in_(task_ids))).mappings()}
    pending = False
    for report, task_id in zip(reports, task_ids, strict=True):
        row = rows[task_id]
        if row['status'] == 'failed' and (not row['retryable'] or row['attempts'] >= row['max_attempts']):
            raise ValueError('acquisition failed: ' + report['company_code'] + ' / ' + str(row['error_code']))
        if row['status'] != 'success':
            pending = True
            continue
        if row['stage'] != 'committed' or any(row[k] != report[k] for k in ('company_code', 'report_period', 'report_type', 'source_url', 'sha256', 'document_id')):
            raise ValueError('acquired source identity mismatch: ' + report['company_code'])
    return None if pending else [r['document_id'] for r in reports]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--timeout', type=int, default=360)
    args = parser.parse_args()
    if not 30 <= args.timeout <= 900:
        raise ValueError('acquisition timeout outside bounds')
    engine = create_engine(os.environ['DATABASE_URL'])
    try:
        reports = load_reports()
        ids = enqueue_reports(engine, reports)
        started = time.monotonic()
        print('Task 10 official acquisition enqueued/reused:', ', '.join(ids), flush=True)
        while True:
            completed = completed_reports(engine, reports, ids)
            if completed is not None:
                break
            if time.monotonic() - started >= args.timeout:
                raise TimeoutError('acquisition still pending; tasks retained, inspect worker logs before rerunning')
            time.sleep(2)
        result = dict(artifact_ids=completed, task_ids=ids, source_hashes_verified=True)
        Path(args.output).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result), flush=True)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
