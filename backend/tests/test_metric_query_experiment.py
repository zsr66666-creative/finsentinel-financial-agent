from app.metric_query_experiment import plan_queries, balanced_search

def test_aliases_and_multiple_metrics_are_detected_without_case_ids():
    assert plan_queries('营业规模有没有扩大')==['营业收入']
    assert plan_queries('资产规模和归属于上市公司股东的权益分别是多少')==['总资产','归属于上市公司股东的净资产']
    assert plan_queries('营收、应收账款及存货有什么变化')==['营业收入','应收账款','存货']
    assert plan_queries('天气情况如何')==[]

def test_balancing_preserves_scope_and_covers_multiple_metrics():
    rows=[dict(chunk_id='a',text='营业收入 100',company_code='c',period='p'),
          dict(chunk_id='b',text='应收账款 20',company_code='c',period='p'),
          dict(chunk_id='x',text='应收账款 20',company_code='other',period='p')]
    result=balanced_search(rows,'营业收入与应收账款',company_code='c',period='p',top_k=2)
    assert [r['chunk_id'] for r in result['items']]==['a','b']
    assert result['queries']==['营业收入','应收账款']
