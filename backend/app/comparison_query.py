"""Bounded explicit comparison grammar and exact local span alignment.

This module does not establish database presence or infer missing scope/dates.
"""
import re
from datetime import date


def parse_comparison(question):
    rejected=dict(status='needs_review',reason='unsupported_or_ambiguous_query')
    pattern=(r'立讯精密(\d{4})年(\d{1,2})月(\d{1,2})日'
             r'(母公司|合并)(?:报表)?应收账款(?:较|相比)'
             r'(\d{4})年(\d{1,2})月(\d{1,2})日是否(未增加|增加)[？?]?')
    if not isinstance(question,str):
        return rejected
    match=re.fullmatch(pattern,question.strip())
    if not match:
        return rejected
    y,m,d,scope,py,pm,pd,relation=match.groups()
    try:
        current=date(int(y),int(m),int(d))
        previous=date(int(py),int(pm),int(pd))
    except ValueError:
        return rejected
    if previous>=current:
        return rejected
    return dict(status='parsed',company='002475',metric='receivables',
                scope='parent' if scope=='母公司' else 'consolidated',
                current_period=current.isoformat(),previous_period=previous.isoformat(),
                relation='not_greater' if relation=='未增加' else 'greater')


def align_metric_span(document,pair,*,page,source_sha):
    if document.get('sha256')!=source_sha or not document.get('id'):
        return None
    expected=['应收账款',pair['current'],pair['previous']]
    hits=[]
    for source_page in document.get('pages',[]):
        if source_page['page']!=page:
            continue
        for index,span in enumerate(source_page.get('spans',[])):
            lines=[line.strip().replace(',','') for line in span.get('text','').splitlines() if line.strip()]
            if lines==expected:
                hits.append(f"{document['id']}-p{page}-s{index}")
    return hits[0] if len(hits)==1 else None
