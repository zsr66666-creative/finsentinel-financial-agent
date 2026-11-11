"""Known-contract development checks; not an independent test set."""
import argparse
import json
from pathlib import Path
from app.persisted_comparison import compare_rows
from scripts.vector_batch import validate


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    package=json.loads(args.package.read_text(encoding='utf-8'))
    validate(package)
    rows=[dict(chunk_id=r['chunk_id'],text_sha256=r['text_sha256'],
        provenance={k:v for k,v in r.items() if k!='embedding'}) for r in package['rows']]
    base='立讯精密2026年6月30日母公司应收账款较2025年12月31日是否未增加？'
    cases=[
        ('parent-explicit',base,'supported',True,rows),
        ('consolidated-positive',base.replace('母公司','合并').replace('未增加','增加'),'supported',False,rows),
        ('supported-wording',base.replace('母公司','母公司报表').replace('较','相比'),'supported',True,rows),
        ('unsupported-synonym',base.replace('应收账款','应收款项'),'needs_review',None,rows),
        ('missing-scope',base.replace('母公司',''),'needs_review',None,rows),
        ('conflicting-scope',base.replace('母公司','母公司与合并'),'needs_review',None,rows),
        ('unreviewed-date',base.replace('2026年','2027年'),'needs_review',None,rows),
        ('invalid-date',base.replace('6月30日','2月30日'),'needs_review',None,rows),
        ('other-company',base.replace('立讯精密','长盈精密'),'needs_review',None,rows),
        ('double-negation',base.replace('未增加','没有不增加'),'needs_review',None,rows),
        ('future-forecast','立讯精密明年应收账款会增加吗？','needs_review',None,rows),
        ('missing-title',base,'needs_review',None,[r for r in rows if 'fulltext' not in r['chunk_id']]),
        ('missing-metric',base,'needs_review',None,[r for r in rows if not r['chunk_id'].endswith('p63-s4')]),
    ]
    results=[]
    for name,question,status,truth,evidence in cases:
        result=compare_rows(question,evidence)
        passed=result['status']==status and result['claim_true'] is truth
        if status=='needs_review':
            passed=passed and result['evidence_ids']==[]
        else:
            passed=passed and len(result['evidence_ids'])==2
        results.append(dict(case_id=name,question=question,expected_status=status,
            expected_claim_true=truth,passed=passed,result=result))
    report=dict(evaluation_type='known_contract_development_boundary_check',
        passed=sum(r['passed'] for r in results),total=len(results),cases=results,
        limitations=['local compare_rows only; not HTTP, PostgreSQL or browser execution',
            'cases authored with current grammar known; not independent or blind evaluation',
            'unsupported synonyms are deliberately refused; no semantic generalization claim'])
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"{report['passed']}/{report['total']} passed")
    if report['passed']!=report['total']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
