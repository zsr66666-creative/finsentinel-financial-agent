from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select, update

from app.ingestion.task_queue import metadata, tasks


def test_source_manifest_binds_official_identity_and_document_hash():
    from scripts.task10_acquire import load_reports
    reports = load_reports()
    assert {r['company_code'] for r in reports} == {'002555', '002230'}
    assert all(r['report_period'] == '2024FY' and r['report_type'] == 'annual' for r in reports)
    assert len({r['document_id'] for r in reports}) == 2


def test_batch_reuses_tasks_and_checks_hash_before_indexing():
    from scripts.task10_acquire import load_reports, enqueue_reports, completed_reports
    engine = create_engine('sqlite:///:memory:')
    metadata.create_all(engine)
    reports = load_reports()
    first = enqueue_reports(engine, reports)
    assert enqueue_reports(engine, reports) == first
    assert completed_reports(engine, reports, first) is None
    with engine.begin() as c:
        for report, task_id in zip(reports, first):
            c.execute(update(tasks).where(tasks.c.id == task_id).values(status='success', stage='committed',
                      sha256=report['sha256'], document_id=report['document_id'], finished_at=datetime.now(timezone.utc)))
    assert completed_reports(engine, reports, first) == [r['document_id'] for r in reports]
    with engine.begin() as c:
        c.execute(update(tasks).where(tasks.c.id == first[0]).values(sha256='bad'))
    with pytest.raises(ValueError, match='source identity'):
        completed_reports(engine, reports, first)
    with engine.connect() as c: assert len(c.execute(select(tasks)).all()) == 2


def test_terminal_failure_stops_batch_without_retrying_unrelated_work():
    from scripts.task10_acquire import load_reports, enqueue_reports, completed_reports
    engine = create_engine('sqlite:///:memory:')
    metadata.create_all(engine)
    reports = load_reports()
    ids = enqueue_reports(engine, reports)
    with engine.begin() as c:
        c.execute(update(tasks).where(tasks.c.id == ids[0]).values(status='failed', error_code='invalid_source'))
    with pytest.raises(ValueError, match='acquisition failed'):
        completed_reports(engine, reports, ids)
