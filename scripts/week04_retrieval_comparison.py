"""Development-only shared-corpus retrieval comparison. Private source stays local."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from time import perf_counter
from statistics import median
from scripts.vector_batch import MODEL, REVISION
from scripts.vector_query import PREFIX
from app.persisted_hybrid import hybrid_search

def usable(text):
    return bool(text.strip()) and not re.search(r'\.{4,}|…{2,}',text) and not (
        '半年度报告全文' in text or text.strip().isdigit())

def build(doc):
    rows=[]
    for page in doc['pages']:
        spans=page.get('spans',[])
        for i,span in enumerate(spans):
            content=span.get('text','').strip()
            if page['page']==2 and i in (3,4): continue
            if page['page']==2 and i==2:
                content='\n'.join(s['text'].strip() for s in spans[2:5])
            if not usable(content): continue
            rows.append(dict(chunk_id=f"{doc['id']}-p{page['page']}-s{i}",text=content,
                company_code=doc['company_code'],period=doc['report_period'],page=page['page'],
                source_url=doc['source_url'],document_sha256=doc['sha256']))
    return rows

SPECS=[('董事会对半年度报告真实性作出了什么保证？',2,2),
       ('营业收入是多少？',8,5),('归属于上市公司股东的净利润是多少？',8,6),
       ('扣除非经常性损益的净利润是多少？',8,7),('经营活动产生的现金流量净额是多少？',8,8),
       ('基本每股收益是多少？',8,9),('稀释每股收益是多少？',8,10),
       ('加权平均净资产收益率是多少？',8,11),('总资产是多少？',8,13),
       ('归属于上市公司股东的净资产是多少？',8,14)]

def main():
    from sentence_transformers import SentenceTransformer
    docs=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(Path('data/derived/documents').glob('*.json'))]
    doc=next(d for d in docs if d['id']=='002475-2026H1')
    rows=build(doc)
    cases=[dict(id=f'w04dev-{i:02}',question=q,gold_evidence_ids=[f"{doc['id']}-p{page}-s{span}"],
                split='development',annotation_status='assistant_source_checked_pending_human_review')
           for i,(q,page,span) in enumerate(SPECS,1)]
    ids={r['chunk_id'] for r in rows}
    assert all(set(c['gold_evidence_ids'])<=ids for c in cases)
    canonical=json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()
    protocol=dict(model=MODEL,revision=REVISION,dimensions=512,corpus_sha256=hashlib.sha256(canonical).hexdigest(),
        cases=cases,bm25=dict(k1=1.2,b=0.75),rrf_k=60,candidate_depth=20,top_k=10,
        limitations=['development only; questions selected after source inspection','gold labels pending human review',
                     'single local PDF copy; official link not independently verified','no held-out/generalization claim'])
    private=Path('outputs/week04-comparison');private.mkdir(parents=True,exist_ok=True)
    (private/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
    started=perf_counter()
    model=SentenceTransformer(MODEL,revision=REVISION,local_files_only=True,device='cpu')
    load_ms=(perf_counter()-started)*1000
    started=perf_counter()
    vectors=model.encode([r['text'] for r in rows],batch_size=8,normalize_embeddings=True)
    index_ms=(perf_counter()-started)*1000
    output=[]
    for case in cases:
        started=perf_counter()
        query=model.encode([PREFIX+case['question']],normalize_embeddings=True)[0]
        encoding_ms=(perf_counter()-started)*1000
        started=perf_counter()
        ranking=sorted(zip(rows,vectors),key=lambda p:(-float(query@p[1]),p[0]['chunk_id']))
        vector_ms=(perf_counter()-started)*1000
        vector_result=dict(items=[{'chunk_id':r['chunk_id']} for r,v in ranking[:20]])
        args=dict(company_code=doc['company_code'],period=doc['report_period'],top_k=10)
        bm25=hybrid_search(rows,case['question'],**args)
        hybrid=hybrid_search(rows,case['question'],vector_search=lambda:vector_result,**args)
        for method,result,latency in [('bm25',bm25,bm25['duration_ms']),
             ('vector',vector_result,encoding_ms+vector_ms),
             ('rrf',hybrid,encoding_ms+vector_ms+hybrid['duration_ms'])]:
            retrieved=[r['chunk_id'] for r in result['items']][:10]
            gold=set(case['gold_evidence_ids'])
            output.append(dict(case_id=case['id'],method=method,retrieved_ids=retrieved,
                recall_at_5=len(gold&set(retrieved[:5]))/len(gold),
                recall_at_10=len(gold&set(retrieved[:10]))/len(gold),duration_ms=round(latency,3),
                miss_reason=None if gold<=set(retrieved[:10]) else 'gold_present_but_ranked_below_10_or_no_lexical_match'))
    summary={}
    for method in ('bm25','vector','rrf'):
        group=[r for r in output if r['method']==method]
        times=sorted(r['duration_ms'] for r in group)
        summary[method]=dict(cases=len(group),hits_at_5=sum(r['recall_at_5']==1 for r in group),
             hits_at_10=sum(r['recall_at_10']==1 for r in group),
             recall_at_5=sum(r['recall_at_5'] for r in group)/len(group),
             recall_at_10=sum(r['recall_at_10'] for r in group)/len(group),
             p50_ms=median(times),p95_ms=times[-1])
    result=dict(protocol=protocol,code_version=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                corpus_chunks=len(rows),model_load_ms=round(load_ms,3),document_encoding_ms=round(index_ms,3),
                timing='local CPU, sequential single pass; query encoding included for vector/RRF; no DB/network',
                summary=summary,details=output)
    Path('data/evals/week04-retrieval-comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(chunks=len(rows),summary=summary),ensure_ascii=False))

if __name__=='__main__': main()
