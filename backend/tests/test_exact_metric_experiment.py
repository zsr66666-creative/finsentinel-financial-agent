from app.exact_metric_experiment import exact_search

def test_exact_numeric_label_and_explicit_scope_outrank_nearby_terms():
    base=dict(company_code='c',period='p')
    rows=[dict(base,chunk_id='finance',text='应收款项融资\n99'),
          dict(base,chunk_id='unknown',text='应收账款\n88'),
          dict(base,chunk_id='consolidated',text='应收账款\n77',explicit_consolidated_page=True),
          dict(base,chunk_id='heading',text='应收账款'),
          dict(base,chunk_id='wrong',text='应收账款\n66',company_code='other')]
    result=exact_search(rows,'应收账款',company_code='c',period='p',top_k=5)
    assert result['items'][0]['chunk_id']=='consolidated'
    assert result['items'][1]['chunk_id']=='unknown'
    assert 'wrong' not in [r['chunk_id'] for r in result['items']]

def test_multiple_metrics_have_distinct_slots_and_wrapped_labels():
    rows=[dict(chunk_id='profit',text='归属于上市公司股东的净\n利润（元）\n100',company_code='c',period='p'),
          dict(chunk_id='cash',text='经营活动产生的现金流量净额（元）\n-20',company_code='c',period='p')]
    assert {r['chunk_id'] for r in exact_search(rows,'归母净利润和经营现金流',company_code='c',period='p')['items']}=={'profit','cash'}
