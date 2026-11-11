import hashlib
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.persisted_comparison import compare_rows, CONTRACTS, SOURCE_SHA

QUESTION='立讯精密2026年6月30日母公司应收账款较2025年12月31日是否未增加？'


def rows():
    contract=CONTRACTS['parent']
    texts=['应收账款\n5,313,841,643.82\n5,620,343,695.37', '2、母公司资产负债表']
    return [dict(chunk_id=key,text_sha256=hashlib.sha256(content.encode()).hexdigest(),
        provenance=dict(text=content,company_code='002475',period='2026H1',
            document_id='002475-2026H1',document_sha256=SOURCE_SHA,page=page,
            statement_scope='parent',scope_evidence_id=contract['title']))
        for key,content,page in [(contract['metric'],texts[0],63),(contract['title'],texts[1],62)]]


def test_database_rows_produce_real_ids_and_comparison():
    result=compare_rows(QUESTION,rows())
    assert result['status']=='supported' and result['claim_true'] is True
    assert result['difference']=='-306502051.55'
    assert set(result['evidence_ids'])=={CONTRACTS['parent']['metric'],CONTRACTS['parent']['title']}


@pytest.mark.parametrize('field,value',[('document_sha256','bad'),('page',60),
    ('company_code','other'),('statement_scope','consolidated'),('text','应收账款\n1.00\n2.00')])
def test_mismatched_provenance_is_rejected(field,value):
    data=rows(); data[0]['provenance'][field]=value
    assert compare_rows(QUESTION,data)['status']=='needs_review'


def test_missing_title_and_unreviewed_dates_rejected():
    assert compare_rows(QUESTION,rows()[:1])['status']=='needs_review'
    assert compare_rows(QUESTION.replace('2026年','2027年'),rows())['status']=='needs_review'


def test_http_validation_and_unavailable_evidence():
    with TestClient(create_app('sqlite:///:memory:',data_mode='real_corpus')) as client:
        assert client.post('/api/v1/evidence/compare',json={'question':''}).status_code==422
        response=client.post('/api/v1/evidence/compare',json={'question':QUESTION})
        assert response.status_code==503
        assert response.json()['detail']=='comparison_evidence_unavailable'
        response=client.post('/api/v1/evidence/compare',json={'question':'明年会增加吗？'})
        assert response.status_code==200 and response.json()['status']=='needs_review'


def test_http_success_uses_database_reader(monkeypatch):
    calls=[]
    def reader(engine,question):
        calls.append(question)
        return compare_rows(question,rows())
    monkeypatch.setattr('app.main.compare_persisted',reader)
    with TestClient(create_app('sqlite:///:memory:',data_mode='real_corpus')) as client:
        result=client.post('/api/v1/evidence/compare',json={'question':QUESTION})
        assert result.status_code==200 and result.json()['claim_true'] is True
        assert calls==[QUESTION]
