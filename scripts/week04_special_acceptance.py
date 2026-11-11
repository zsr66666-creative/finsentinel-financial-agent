"""Audit scope, negation and fallback; record limitations rather than hide them."""
import json
from pathlib import Path
from app.exact_metric_experiment import exact_search
from app.persisted_hybrid import hybrid_search
from scripts.week04_approved_eval import sha

def run():
    documents=[json.loads(p.read_text(encoding='utf-8')) for p in Path('data/derived/documents').glob('*.json')]
    doc=next(d for d in documents if d['id']=='002475-2026H1')
    rows=[]
    for page in doc['pages']:
        explicit=any('合并资产负债表' in s.get('text','') for s in page['spans'])
        for i,s in enumerate(page['spans']):
            if s.get('text','').strip():
                rows.append(dict(chunk_id=f"{doc['id']}-p{page['page']}-s{i}",text=s['text'].strip(),
                    company_code=doc['company_code'],period=doc['report_period'],page=page['page'],
                    explicit_consolidated_page=explicit))
    scope=dict(company_code='002475',period='2026H1',top_k=5)
    records=[]
    for label,question,target in [
        ('consolidated','合并资产负债表应收账款是多少？','002475-2026H1-p60-s20'),
        ('parent','母公司资产负债表应收账款是多少？','002475-2026H1-p63-s4')]:
        result=exact_search(rows,question,**scope)
        ids=[r['chunk_id'] for r in result['items']]
        records.append(dict(check=f'statement_scope_{label}',status='PASS' if ids and ids[0]==target else 'FAIL',
            question=question,expected_first=target if label=='consolidated' else None,actual_ids=ids,
            scope_note='parent query must not prioritize explicitly consolidated row; p63 candidate scope remains unverified' if label=='parent' else 'same-page consolidated title'))
    # A page without a same-page title is not proof of a parent statement.
    continuation=[r for r in rows if r['page']==63 and r['chunk_id'].endswith('-s4')]
    result=exact_search(continuation,'合并报表应收账款是多少？',**scope)
    records.append(dict(check='unknown_continuation_scope',status='FAIL' if result['items'] else 'PASS',
        actual_ids=[r['chunk_id'] for r in result['items']],
        reason='retriever returns unclassified row without scope warning; missing page context'))
    for label,question in [('negation','营业收入是否没有增长？'),('missing_evidence','2027年7月营业收入预测是多少？')]:
        result=exact_search(rows,question,**scope)
        records.append(dict(check=label,status='NOT_MEASURED',question=question,
            returned_ids=[r['chunk_id'] for r in result['items']],
            reason='candidate-only interface has no answer support/negation decision; cannot score correct refusal'))
    small=[dict(chunk_id='inventory',text='存货 100',company_code='002475',period='2026H1')]
    failures={'timeout':TimeoutError('private diagnostic'),
              'invalid_vector':ValueError('invalid dimension'),
              'provider_failure':RuntimeError('private diagnostic')}
    for name,error in failures.items():
        def broken(): raise error
        result=hybrid_search(small,'存货',vector_search=broken,**scope)
        ok=(result['retrieval_mode']=='bm25_only' and [r['chunk_id'] for r in result['items']]==['inventory']
            and result['warnings']==[f'vector_unavailable:{type(error).__name__}'])
        records.append(dict(check=f'fallback_{name}',status='PASS' if ok else 'FAIL',
            mode=result['retrieval_mode'],warnings=result['warnings']))
    for name,callback,warning in [('disabled',None,'vector_not_configured'),
                                 ('empty',lambda:dict(items=[]),'vector_empty')]:
        result=hybrid_search(small,'存货',vector_search=callback,**scope)
        records.append(dict(check=f'fallback_{name}',status='PASS' if result['retrieval_mode']=='bm25_only'
            and result['warnings']==[warning] and result['items'] else 'FAIL',warnings=result['warnings']))
    result=dict(date='2026-11-11',source_pdf_sha256=doc['sha256'],
        algorithm_sha256=sha(Path('backend/app/exact_metric_experiment.py').read_bytes()),
        conditions='real local sparse extracted pages for scope; injected failures for degradation, no live provider fault',
        production_default_change='blocked by scope and support gaps; no deployment performed',
        counts={s:sum(r['status']==s for r in records) for s in ['PASS','FAIL','NOT_MEASURED']},checks=records)
    return result

if __name__=='__main__':
    result=run()
    Path('data/evals/week04-special-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
