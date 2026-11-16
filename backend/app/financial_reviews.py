"""Append-only decisions bound to server-verified financial snapshots, never demo alerts."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4
from sqlalchemy import (MetaData, Table, Column, String, JSON, Index, select, text, inspect)

metadata = MetaData()
review_table = Table('financial_reviews', metadata,
    Column('id', String(36), primary_key=True),
    Column('company_code', String(6), nullable=False),
    Column('period', String(20), nullable=False),
    Column('statement_scope', String(30), nullable=False),
    Column('metric', String(50), nullable=False),
    Column('fingerprint', String(64), nullable=False),
    Column('idempotency_key', String(100), nullable=False, unique=True),
    Column('request_sha256', String(64), nullable=False),
    Column('created_at', String(40), nullable=False),
    Column('payload', JSON, nullable=False))
Index('ix_financial_review_scope', review_table.c.company_code, review_table.c.period,
      review_table.c.statement_scope, review_table.c.metric, review_table.c.fingerprint)
MIGRATION = '005_financial_reviews'
DECISIONS = ('confirmed', 'rejected', 'needs_evidence')

class ReviewConflict(ValueError): pass
class ReviewUnavailable(ValueError): pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def snapshot_fingerprint(metric):
    return hashlib.sha256(canonical(metric).encode()).hexdigest()


def migrate_reviews(engine):
    from app.migrations import _ensure_version_table
    with engine.begin() as c:
        if engine.dialect.name == 'postgresql':
            c.execute(text('SELECT pg_advisory_xact_lock(572012)'))
        _ensure_version_table(c)
        existing = c.execute(text('SELECT 1 FROM schema_migrations WHERE name=:name'), {'name': MIGRATION}).first()
        if existing:
            if not inspect(c).has_table('financial_reviews'):
                raise ValueError('financial review migration/schema mismatch')
            return []
        if inspect(c).has_table('financial_reviews'):
            raise ValueError('unversioned financial review table')
        metadata.create_all(c)
        c.execute(text('INSERT INTO schema_migrations(name,applied_at) VALUES(:name,:at)'),
                  dict(name=MIGRATION, at=datetime.now(timezone.utc).isoformat()))
    return [MIGRATION]


def _scope(comparison, metric=None):
    expression = ((review_table.c.company_code == comparison['company_code']) &
                  (review_table.c.period == comparison['period']) &
                  (review_table.c.statement_scope == comparison['statement_scope']))
    return expression & (review_table.c.metric == metric) if metric else expression


def review_state(engine, comparison):
    result = []
    with engine.connect() as c:
        # Query latest matching fingerprint independently of bounded history so
        # a long history can never silently drop the effective decision.
        for metric in comparison['items']:
            fingerprint = snapshot_fingerprint(metric) if metric['status'] == 'supported' else None
            query = select(review_table.c.payload).where(_scope(comparison, metric['metric']))
            order = (review_table.c.created_at.desc(), review_table.c.id.desc())
            history = list(c.execute(query.order_by(*order).limit(30)).scalars())
            latest = c.execute(query.where(review_table.c.fingerprint == fingerprint).order_by(*order).limit(1)).scalar() if fingerprint else None
            if latest and not any(r['id'] == latest['id'] for r in history):
                history = history[:29] + [latest]
            result.append(dict(metric=metric['metric'], fingerprint=fingerprint,
                review_status=('source_unavailable' if fingerprint is None else latest['decision'] if latest else 'pending_human'),
                snapshot=metric if fingerprint else None, latest=latest, history=history, history_limit=30))
    return dict(company_code=comparison['company_code'], period=comparison['period'],
                statement_scope=comparison['statement_scope'], items=result,
                identity_assurance='self_declared_operator')


def submit_review(engine, comparison, body):
    metric = next((m for m in comparison['items'] if m['metric'] == body['metric']), None)
    if not metric or metric['status'] != 'supported':
        raise ReviewUnavailable('source_not_supported')
    fingerprint = snapshot_fingerprint(metric)
    if body['fingerprint'] != fingerprint:
        raise ReviewConflict('source_snapshot_changed')
    if body['decision'] not in DECISIONS or not body['reason'].strip() or not body['reviewer'].strip():
        raise ValueError('decision_reason_and_reviewer_required')
    request_hash = hashlib.sha256(canonical(dict(body, company_code=comparison['company_code'],
        period=comparison['period'], statement_scope=comparison['statement_scope'])).encode()).hexdigest()
    # A single lock is deliberate: a small operator-only workflow, <=10 writes/min.
    # It covers idempotency and optimistic latest-id checks in one transaction.
    with engine.connect() as c:
        try:
            if engine.dialect.name == 'sqlite': c.exec_driver_sql('BEGIN IMMEDIATE')
            elif engine.dialect.name == 'postgresql': c.execute(text('SELECT pg_advisory_xact_lock(572012)'))
            else: raise ReviewUnavailable('unsupported_database')
            old = c.execute(select(review_table).where(review_table.c.idempotency_key == body['idempotency_key'])).mappings().first()
            if old:
                if old['request_sha256'] != request_hash: raise ReviewConflict('idempotency_conflict')
                c.commit()
                return old['payload']
            latest = c.execute(select(review_table.c.id).where(_scope(comparison, metric['metric']) &
                (review_table.c.fingerprint == fingerprint)).order_by(review_table.c.created_at.desc(), review_table.c.id.desc()).limit(1)).scalar()
            if latest != body['expected_review_id']: raise ReviewConflict('review_version_changed')
            record = dict(id=str(uuid4()), company_code=comparison['company_code'], period=comparison['period'],
                statement_scope=comparison['statement_scope'], metric=metric['metric'], fingerprint=fingerprint,
                decision=body['decision'], reason=body['reason'].strip(), reviewer=body['reviewer'].strip(),
                identity_assurance='self_declared_operator', created_at=datetime.now(timezone.utc).isoformat(),
                previous_review_id=latest, snapshot=json.loads(canonical(metric)))
            c.execute(review_table.insert().values(**{k:record[k] for k in ('id','company_code','period','statement_scope','metric','fingerprint','created_at')},
                idempotency_key=body['idempotency_key'], request_sha256=request_hash, payload=record))
            c.commit()
            return record
        except Exception:
            c.rollback()
            raise
