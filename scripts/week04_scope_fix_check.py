"""Reproduce scope fixes on real sparse pages without changing old artifacts."""
import json
from pathlib import Path
from app.statement_scope import scoped_search
from scripts.week04_approved_eval import sha

def main():
    doc=next(json.loads(p.read_text(encoding='utf-8')) for p in Path('data/derived/documents').glob('*.json')
        if json.loads(p.read_text(encoding='utf-8'))['id']=='002475-2026H1')
    rows=[dict(chunk_id=f"{doc['id']}-p{page['page']}-s{i}",text=s.get('text','').strip(),
        company_code=doc['company_code'],period=doc['report_period'],document_id=doc['id'],page=page['page'])
        for page in doc['pages'] for i,s in enumerate(page['spans']) if s.get('text','').strip()]
    kwargs=dict(company_code='002475',period='2026H1')
    checks=[]
    consolidated=scoped_search(rows,'合并报表应收账款是多少？',**kwargs)
    checks.append(dict(name='consolidated_metric',passed=bool(consolidated['items']) and
        consolidated['items'][0]['chunk_id']=='002475-2026H1-p60-s20',result=consolidated))
    parent=scoped_search(rows,'母公司资产负债表应收账款是多少？',**kwargs)
    checks.append(dict(name='parent_without_verified_header_blocks',passed=not parent['items'] and
        parent['status']=='needs_review',result=parent))
    continuation=scoped_search([r for r in rows if r['chunk_id']=='002475-2026H1-p63-s4'],
        '合并报表应收账款是多少？',**kwargs)
    checks.append(dict(name='unknown_continuation_blocks',passed=not continuation['items'] and
        'statement_scope_unverified' in continuation['warnings'],result=continuation))
    output=dict(date='2026-11-11',pdf_sha256=doc['sha256'],
        fix_code_sha256=sha(Path('backend/app/statement_scope.py').read_bytes()),
        checks=checks,passed=sum(c['passed'] for c in checks),
        limitations=['parent amount not verified: sparse corpus lacks required header context',
            'candidate scope checks do not verify answer semantics, negation or refusal quality',
            'new opt-in module; production and frozen historical ranking unchanged'])
    # Public audit keeps IDs and scope anchors, not full report text.
    for check in checks:
        check['result']['items']=[dict(chunk_id=r['chunk_id'],statement_scope=r['provenance']['statement_scope'],
            scope_evidence_id=r['provenance']['scope_evidence_id']) for r in check['result']['items']]
    Path('data/evals/week04-scope-fix-check.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=output['passed'],total=len(checks))))
    if not all(c['passed'] for c in checks): raise SystemExit(1)

if __name__=='__main__':main()
