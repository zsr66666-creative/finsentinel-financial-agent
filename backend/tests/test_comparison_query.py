import pytest
from app.comparison_query import parse_comparison, align_metric_span


def test_explicit_query_and_negation():
    result=parse_comparison('立讯精密2026年6月30日母公司应收账款较2025年12月31日是否未增加？')
    assert result['status']=='parsed'
    assert result['relation']=='not_greater'
    assert result['scope']=='parent'
    assert result['current_period']=='2026-06-30'


@pytest.mark.parametrize('question',[
    '立讯精密明年应收账款会增加吗？',
    '立讯精密2026年6月30日应收账款较2025年12月31日是否增加？',
    '立讯精密2026年6月30日母公司应收账款较2025年12月31日是否没有不增加？',
    '其他公司2026年6月30日母公司应收账款较2025年12月31日是否增加？',
    '立讯精密2026年2月30日母公司应收账款较2025年12月31日是否增加？',
    '立讯精密2025年6月30日母公司应收账款较2025年12月31日是否增加？',
])
def test_ambiguous_or_unsupported_query_is_rejected(question):
    assert parse_comparison(question)['status']=='needs_review'


def doc(spans):
    return dict(id='d',sha256='hash',pages=[dict(page=63,spans=spans)])


def test_alignment_requires_unique_content_page_and_hash():
    pair=dict(current='5313841643.82',previous='5620343695.37')
    span=dict(text='应收账款\n5,313,841,643.82\n5,620,343,695.37')
    assert align_metric_span(doc([span]),pair,page=63,source_sha='hash')=='d-p63-s0'
    assert align_metric_span(doc([span,span]),pair,page=63,source_sha='hash') is None
    assert align_metric_span(doc([span]),pair,page=60,source_sha='hash') is None
    assert align_metric_span(doc([span]),pair,page=63,source_sha='other') is None
