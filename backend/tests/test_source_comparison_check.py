from scripts.week04_source_comparison_check import extract_pair


def test_missing_or_ambiguous_rows_are_not_accepted():
    assert extract_pair([], 'parent') is None
    row=dict(text='应收账款',statement_scope='parent',scope_title_page=1,page=2,line=0)
    assert extract_pair([row], 'parent') is None
    rows=[row,dict(row,text='1.00',line=1),dict(row,text='2.00',line=2)]
    assert extract_pair(rows, 'parent')['current']=='1.00'
    assert extract_pair(rows+rows, 'parent') is None


def test_values_cannot_cross_page_or_scope():
    row=dict(text='应收账款',statement_scope='parent',scope_title_page=1,page=2,line=0)
    rows=[row,dict(row,text='1.00',line=1),dict(row,text='2.00',line=2,page=3)]
    assert extract_pair(rows, 'parent') is None
