from scripts.week04_approved_eval import score, scope_rows

def test_multi_evidence_recall_is_fractional_and_strict_is_separate():
    result=score(['a','b'],['a','irrelevant'])
    assert result['recall_at_5']==0.5
    assert result['all_gold_at_5'] is False
    assert score([],['a'])['recall_at_5'] is None

def test_negative_allowlist_and_company_period_are_enforced():
    rows=[dict(chunk_id='a',company_code='c',period='p'),
          dict(chunk_id='b',company_code='c',period='p'),
          dict(chunk_id='wrong',company_code='other',period='p')]
    assert [r['chunk_id'] for r in scope_rows(rows,dict(company_code='c',period='p',allowed_ids=['a']))]==['a']
    assert scope_rows(rows,dict(company_code='missing',period='p',allowed_ids=None))==[]
