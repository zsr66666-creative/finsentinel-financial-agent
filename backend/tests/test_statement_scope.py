from app.statement_scope import annotate_scope, scoped_search

def row(key,content,page=1,doc='d',company='c'):
    return dict(chunk_id=key,text=content,page=page,document_id=doc,company_code=company,period='p')

def test_headers_apply_only_forward_on_same_document_and_page():
    rows=[row('pre','应收账款\n1'),row('h','1、合并资产负债表'),row('a','应收账款\n2'),
          row('hp','2、母公司资产负债表'),row('b','应收账款\n3'),row('next','应收账款\n4',2),
          row('other','应收账款\n5',doc='other')]
    result={r['chunk_id']:r for r in annotate_scope(rows)}
    assert result['pre']['statement_scope']=='unknown'
    assert result['a']['statement_scope']=='consolidated'
    assert result['a']['scope_evidence_id']=='h'
    assert result['b']['statement_scope']=='parent'
    assert result['next']['statement_scope']==result['other']['statement_scope']=='unknown'

def test_explicit_parent_excludes_consolidated_and_unknown():
    rows=[row('h','合并资产负债表'),row('a','应收账款\n2'),
          row('hp','母公司资产负债表',2),row('b','应收账款\n3',2),row('u','应收账款\n4',3)]
    result=scoped_search(rows,'母公司应收账款是多少',company_code='c',period='p')
    assert [r['chunk_id'] for r in result['items']]==['b']
    assert result['requested_scope']=='parent'

def test_unknown_scope_empty_is_review_not_verified_refusal():
    result=scoped_search([row('u','存货\n1',2)],'合并报表存货',company_code='c',period='p')
    assert result['items']==[]
    assert result['status']=='needs_review'
    assert 'statement_scope_unverified' in result['warnings']
    assert result['answer_verified'] is False

def test_scope_conflict_and_unclassified_implicit_query():
    rows=[row('u','存货\n1')]
    assert scoped_search(rows,'合并与母公司存货',company_code='c',period='p')['items']==[]
    implicit=scoped_search(rows,'存货是多少',company_code='c',period='p')
    assert implicit['items'] and implicit['status']=='needs_review'

def test_other_table_ends_scope_and_as_of_excludes_unknown_date():
    rows=[row('h','合并资产负债表'),row('a','存货\n2'),row('end','合并利润表'),row('b','存货\n3')]
    assert annotate_scope(rows)[-1]['statement_scope']=='unknown'
    result=scoped_search(rows,'合并报表存货',company_code='c',period='p',as_of='2026-01-01')
    assert result['items']==[]

def test_prose_is_not_title_and_untrusted_existing_tags_are_overwritten():
    rows=[row('mention','本附注应结合合并资产负债表阅读。'),
          dict(row('a','存货\n3'),statement_scope='parent',explicit_consolidated_page=True)]
    assert all(r['statement_scope']=='unknown' for r in annotate_scope(rows))
    assert scoped_search(rows,'母公司存货',company_code='c',period='p')['items']==[]
