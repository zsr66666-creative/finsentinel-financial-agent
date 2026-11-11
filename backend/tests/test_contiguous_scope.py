from app.contiguous_scope import annotate_complete_pages

def page(n,text,complete=True):
    return dict(page=n,text=text,complete=complete)

def test_contiguous_complete_pages_carry_title_but_gaps_do_not():
    result=annotate_complete_pages('d',[page(1,'母公司资产负债表'),page(2,'应收账款\n10'),page(4,'存货\n20')])
    assert next(r for r in result if r['page']==2)['statement_scope']=='parent'
    assert next(r for r in result if r['page']==2)['scope_title_page']==1
    assert next(r for r in result if r['page']==4)['statement_scope']=='unknown'

def test_incomplete_page_and_other_table_stop_context():
    result=annotate_complete_pages('d',[page(1,'合并资产负债表'),page(2,'missing',False),page(3,'存货'),page(4,'母公司资产负债表\n存货'),page(5,'合并利润表\n营业收入')])
    assert next(r for r in result if r['page']==3)['statement_scope']=='unknown'
    assert result[-1]['statement_scope']=='unknown'
