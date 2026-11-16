import pytest
from sqlalchemy import create_engine
from app.personal_research import ResearchLibrary, migrate_research_library
from app.store import Store
from app.auth.service import migrate_accounts


def test_private_durable_library(tmp_path):
    url='sqlite:///'+str(tmp_path/'library.db')
    store=Store(url);store.put('companies',{'id':'000001','name':'Company'})
    migrate_accounts(store.engine);migrate_research_library(store.engine)
    library=ResearchLibrary(store)
    first=library.favorite('alice',kind='company',company_code='000001')
    assert library.favorite('alice',kind='company',company_code='000001')['id']==first['id']
    assert library.listing('bob')['total']==0
    with pytest.raises(ValueError,match='not_found'): library.note('bob',first['id'],'private')
    library.note('alice',first['id'],'private')
    assert ResearchLibrary(Store(url)).listing('alice')['items'][0]['note']=='private'
    with pytest.raises(ValueError):library.favorite('alice',kind='company',company_code='missing')
    with pytest.raises(ValueError):library.note('alice',first['id'],'x'*1001)


def test_history_bounded_and_safe(tmp_path):
    store=Store('sqlite:///'+str(tmp_path/'history.db'));migrate_accounts(store.engine);migrate_research_library(store.engine)
    library=ResearchLibrary(store)
    for i in range(203):library.record('alice',kind='compare',query='question '+str(i))
    result=library.listing('alice',history=True,limit=3)
    assert result['total']==200 and len(result['items'])==3
    assert result['items'][0]['href'].startswith('/compare?')
    library.clear('bob');assert library.listing('alice',history=True)['total']==200
    library.clear('alice');assert library.listing('alice',history=True)['total']==0

def test_evidence_snapshot_is_server_derived(tmp_path):
    import json
    from sqlalchemy import text
    store=Store('sqlite:///'+str(tmp_path/'evidence.db'));migrate_accounts(store.engine);migrate_research_library(store.engine)
    with store.engine.begin() as c:
        c.execute(text('CREATE TABLE document_chunk_embeddings (chunk_id TEXT PRIMARY KEY, text_sha256 TEXT, provenance JSON)'))
        c.execute(text('INSERT INTO document_chunk_embeddings VALUES (:id,:hash,:p)'),{'id':'chunk-1','hash':'server-hash','p':json.dumps({'company_code':'000001','period':'2024FY','text':'Original report','page':9,'document_sha256':'document-hash','document_id':'report'})})
    service=ResearchLibrary(store)
    row=service.favorite('alice',kind='evidence',company_code='000001',chunk_id='chunk-1')
    assert row['period']=='2024FY' and row['snapshot']['text']=='Original report'
    assert row['snapshot']['text_sha256']=='server-hash' and row['snapshot']['page']==9
    with pytest.raises(ValueError):service.favorite('alice',kind='evidence',company_code='000002',chunk_id='chunk-1')
    with store.engine.begin() as c:c.execute(text('DELETE FROM document_chunk_embeddings'))
    assert service.listing('alice')['items'][0]['snapshot']['text']=='Original report'

def test_favorite_filters_before_pagination(tmp_path):
    store=Store('sqlite:///'+str(tmp_path/'filters.db'));migrate_accounts(store.engine);migrate_research_library(store.engine)
    store.put('companies',{'id':'000001','name':'First'});store.put('companies',{'id':'000002','name':'Second'})
    service=ResearchLibrary(store)
    first=service.favorite('alice',kind='company',company_code='000001')
    service.favorite('alice',kind='company',company_code='000002')
    result=service.listing('alice',kind='company',company_code='000001',limit=1)
    assert result['total']==1 and result['items'][0]['id']==first['id']
    assert service.listing('bob',kind='company',company_code='000001')['total']==0
    assert service.listing('alice',kind='evidence')['total']==0
    assert service.listing('alice',company_code='000001',offset=1)['items']==[]
