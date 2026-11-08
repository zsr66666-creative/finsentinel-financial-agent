from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import JSON, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def record_model(name, table):
    return type(name, (Base,), {'__tablename__': table, '__annotations__': {'id': Mapped[str], 'payload': Mapped[dict]}, 'id': mapped_column(String(100), primary_key=True), 'payload': mapped_column(JSON, nullable=False)})


TABLES = ['companies', 'filings', 'document_chunks', 'financial_metrics', 'evidence_spans', 'alerts', 'analysis_runs', 'agent_steps', 'tool_calls', 'feedback', 'eval_cases', 'eval_runs', 'prompt_versions', 'ingestion_jobs']
MODELS = {table: record_model(''.join(w.title() for w in table.split('_')), table) for table in TABLES}


class Store:
    def __init__(self, url, create_schema=True):
        options = {'connect_args': {'check_same_thread': False}} if url.startswith('sqlite') else {}
        if url in ('sqlite://', 'sqlite:///:memory:'):
            options['poolclass'] = StaticPool
        self.engine = create_engine(url, **options)
        if create_schema:
            Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def all(self, table):
        with self.sessions() as session:
            return [r.payload for r in session.scalars(select(MODELS[table]).order_by(MODELS[table].id)).all()]

    def get(self, table, key):
        with self.sessions() as session:
            record = session.get(MODELS[table], key)
            return record.payload if record else None

    def put(self, table, value):
        with self.sessions.begin() as session:
            record = session.get(MODELS[table], value['id'])
            if record:
                record.payload = value
            else:
                session.add(MODELS[table](id=value['id'], payload=value))
        return value

    def feedback_transaction(self, *, feedback, alert, candidate=None):
        with self.sessions.begin() as session:
            session.add(MODELS['feedback'](id=feedback['id'], payload=feedback))
            alert_record = session.get(MODELS['alerts'], alert['id'])
            if alert_record is None:
                raise ValueError('alert not found')
            alert_record.payload = alert
            if candidate is not None:
                session.add(MODELS['eval_cases'](id=candidate['id'], payload=candidate))
        return feedback
    def close(self):
        self.engine.dispose()

