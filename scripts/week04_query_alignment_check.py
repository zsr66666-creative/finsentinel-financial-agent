"""Private PDF + existing local chunks -> explicit query -> evidence comparison."""
import argparse
import hashlib
import json
from pathlib import Path
import pymupdf
from app.comparison_query import parse_comparison,align_metric_span
from app.contiguous_scope import annotate_complete_pages
from app.evidence_comparison import compare_evidence
from scripts.week04_source_comparison_check import SOURCE_SHA,extract_pair


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdf',type=Path,required=True)
    parser.add_argument('--documents',type=Path,default=Path('data/derived/documents'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if hashlib.sha256(args.pdf.read_bytes()).hexdigest()!=SOURCE_SHA:
        raise ValueError('source checksum mismatch')
    documents=[json.loads(p.read_text(encoding='utf-8')) for p in args.documents.glob('*.json')]
    matches=[d for d in documents if d['id']=='002475-2026H1' and d['sha256']==SOURCE_SHA]
    if len(matches)!=1:
        raise ValueError('unique matching local document required')
    document=matches[0]
    with pymupdf.open(args.pdf) as pdf:
        pages=[dict(page=n,text=pdf[n-1].get_text(),complete=True) for n in range(60,64)]
    rows=annotate_complete_pages(document['id'],pages)
    cases=[]
    for label,page,scope in [('母公司',63,'parent'),('合并',60,'consolidated')]:
        pair=extract_pair(rows,scope)
        if pair is None:
            raise ValueError('source row missing')
        chunk=align_metric_span(document,pair,page=page,source_sha=SOURCE_SHA)
        if chunk is None:
            raise ValueError('source and local chunk do not uniquely match')
        for wording,truth in [('增加',False),('未增加',True)]:
            question=f'立讯精密2026年6月30日{label}应收账款较2025年12月31日是否{wording}？'
            plan=parse_comparison(question)
            assert plan['status']=='parsed' and plan['scope']==scope
            # Only the reviewed document's exact date pair is admitted.
            assert (plan['current_period'],plan['previous_period'])==('2026-06-30','2025-12-31')
            base=dict(company=plan['company'],metric=plan['metric'],unit='CNY',scope=plan['scope'],evidence_ids=[chunk])
            result=compare_evidence(dict(base,value=pair['current'],period=plan['current_period']),
                dict(base,value=pair['previous'],period=plan['previous_period']),relation=plan['relation'])
            assert result['status']=='supported' and result['claim_true'] is truth
            cases.append(dict(question=question,plan=plan,result=result,
                scope_source=pair['evidence_ids'][0],local_chunk_aligned=True,database_presence='not_verified'))
    report=dict(source_sha256=SOURCE_SHA,cases=cases,passed=len(cases),
        limitations=['bounded grammar, not general language understanding',
            'dates and unit are the human-reviewed exact-document contract',
            'scope title audit anchor is not a persisted chunk ID',
            'local span alignment only; Alibaba database presence not verified',
            'production website and API unchanged'])
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'PASS: {len(cases)} query-to-local-chunk comparison cases')


if __name__=='__main__':
    main()
