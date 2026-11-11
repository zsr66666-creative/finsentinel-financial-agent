"""Bounded source-to-comparison acceptance; not a production QA endpoint."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import pymupdf
from app.contiguous_scope import annotate_complete_pages
from app.evidence_comparison import compare_evidence

SOURCE_SHA='841a3271cddd0e0e6bf9d60e39bda69fa48de13c67300c313395d849bddfa588'


def extract_pair(rows, scope):
    hits=[i for i,r in enumerate(rows) if r['text']=='应收账款'
          and r['statement_scope']==scope and r.get('scope_title_page')]
    if len(hits)!=1:
        return None
    i=hits[0]
    group=rows[i:i+3]
    if len(group)!=3 or any(r['page']!=group[0]['page'] or
        r['statement_scope']!=scope or r['line']!=group[0]['line']+j
        for j,r in enumerate(group)):
        return None
    if any(not re.fullmatch(r'(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}',r['text']) for r in group[1:]):
        return None
    return dict(current=group[1]['text'].replace(',',''),
                previous=group[2]['text'].replace(',',''),
                evidence_ids=[f"002475-2026H1-p{group[0]['scope_title_page']}-scope",
                              f"002475-2026H1-p{group[0]['page']}-line{group[0]['line']}"])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdf',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if hashlib.sha256(args.pdf.read_bytes()).hexdigest()!=SOURCE_SHA:
        raise ValueError('source PDF checksum mismatch')
    with pymupdf.open(args.pdf) as doc:
        pages=[dict(page=n,text=doc[n-1].get_text(),complete=True) for n in range(60,64)]
    rows=annotate_complete_pages('002475-2026H1',pages)
    # Dates/units below are a human-reviewed contract for this exact PDF only.
    pairs={scope:extract_pair(rows,scope) for scope in ('parent','consolidated')}
    expected={'parent':('5313841643.82','5620343695.37'),
              'consolidated':('47666294604.50','48438796114.12')}
    cases=[]
    evidence={}
    for scope,pair in pairs.items():
        if pair is None or (pair['current'],pair['previous'])!=expected[scope]:
            raise ValueError(f'unexpected source extraction: {scope}')
        base=dict(company='002475',metric='receivables',unit='CNY',scope=scope,
                  evidence_ids=pair['evidence_ids'])
        current=dict(base,value=pair['current'],period='2026-06-30')
        previous=dict(base,value=pair['previous'],period='2025-12-31')
        evidence[scope]=(current,previous)
        for relation,truth in [('greater',False),('not_greater',True)]:
            result=compare_evidence(current,previous,relation=relation)
            assert result['status']=='supported' and result['claim_true'] is truth
            cases.append(dict(case_id=f'{scope}-{relation}',passed=True,result=result))
    current,previous=evidence['parent']
    rejects=[('mixed-scope',current,evidence['consolidated'][1],'greater'),
             ('missing-source',dict(current,evidence_ids=[]),previous,'greater'),
             ('forecast',current,previous,'will_grow')]
    for name,a,b,relation in rejects:
        result=compare_evidence(a,b,relation=relation)
        assert result['status']=='needs_review' and not result['evidence_ids']
        cases.append(dict(case_id=name,passed=True,result=result))
    report=dict(pdf_sha256=SOURCE_SHA,human_review='user confirmed physical pages 62-63, dates and CNY unit in chat',
                evidence=pairs,cases=cases,passed=len(cases),
                limitations=['explicit metric/scope/relation inputs; no natural-language parser',
                             'source line IDs are audit anchors, not persisted chunk IDs',
                             'single reviewed PDF, no independent generalization measurement',
                             'production API and Alibaba database unchanged'])
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: {len(cases)} bounded source-to-comparison cases')


if __name__=='__main__':
    main()
