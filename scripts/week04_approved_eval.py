"""Frozen user-reviewed 16-case DEVELOPMENT comparison; no production writes."""
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from statistics import median
from time import perf_counter
from app.persisted_hybrid import hybrid_search
from scripts.vector_batch import MODEL, REVISION
from scripts.vector_query import PREFIX
from scripts.week04_retrieval_comparison import usable

DOCS=['002475-2026H1','002475-2024FY','002475-2025FY','002241-2026H1']
# Document and raw-span anchors frozen from the user-approved Markdown.
ANCHORS=[(0,[(8,6),(8,8)]),(0,[(8,13),(8,14)]),(3,[(8,8)]),
    (2,[(8,15)]),(1,[(8,15)]),(3,[(8,5)]),(2,[(8,15)]),
    (1,[(8,18)]),(0,[(8,5),(60,20),(60,30)]),(0,[(8,9),(8,10)]),
    (0,[(8,5),(8,6)]),(3,[(8,6),(8,8)])]+[(0,[])]*4
NEGATIVE_IDS=[f'002475-2026H1-p{p}-s{s}' for p,s in [(8,5),(8,6),(8,8),(60,20),(60,30)]]

def sha(data): return hashlib.sha256(data).hexdigest()

def scope_rows(rows,case):
    allowed=case.get('allowed_ids')
    return [r for r in rows if r['company_code']==case['company_code'] and r['period']==case['period']
            and (allowed is None or r['chunk_id'] in allowed)]

def score(gold_ids, retrieved):
    gold=set(gold_ids)
    result={}
    for k in (5,10):
        hits=gold&set(retrieved[:k])
        result[f'recall_at_{k}']=len(hits)/len(gold) if gold else None
        result[f'all_gold_at_{k}']=gold<=set(retrieved[:k]) if gold else None
        result[f'missing_at_{k}']=sorted(gold-hits)
    return result

def freeze():
    source=Path('docs/week04-retrieval-candidate-questions.md').read_bytes()
    sections=re.split(r'### Q\d{2}[^\n]*\n',source.decode('utf-8'))[1:]
    assert len(sections)==16
    cases=[]
    for i,(section,(doc_index,anchors)) in enumerate(zip(sections,ANCHORS),1):
        question=re.search(r'^- 问题：(.*)$',section,re.M).group(1)
        doc=DOCS[doc_index]
        cases.append(dict(id=f'Q{i:02}',question=question,company_code=doc.split('-')[0],
            period=doc.split('-')[1],document_id=doc,
            gold_evidence_ids=[f'{doc}-p{p}-s{s}' for p,s in anchors],
            allowed_ids=NEGATIVE_IDS if i>=13 else None,category=['paraphrase','scope','multi_evidence','insufficient'][((i-1)//4)],
            split='development',annotation_status='human_reviewed',
            review_basis='user approved complete 16-case Markdown and negative scope in this conversation'))
    rows=[]; documents=[]
    for path in sorted(Path('data/derived/documents').glob('*.json')):
        raw=path.read_bytes(); doc=json.loads(raw)
        if doc['id'] not in DOCS: continue
        documents.append(dict(id=doc['id'],pdf_sha256=doc['sha256'],extracted_json_sha256=sha(raw)))
        for page in doc['pages']:
            for i,span in enumerate(page.get('spans',[])):
                content=span.get('text','').strip()
                if not usable(content) or '年度报告全文' in content: continue
                rows.append(dict(chunk_id=f"{doc['id']}-p{page['page']}-s{i}",text=content,
                    company_code=doc['company_code'],period=doc['report_period'],page=page['page'],
                    source_url=doc['source_url'],document_sha256=doc['sha256']))
    assert len(documents)==4 and len({r['chunk_id'] for r in rows})==len(rows)
    for case in cases:
        scoped={r['chunk_id'] for r in scope_rows(rows,case)}
        assert set(case['gold_evidence_ids'])<=scoped
        if case['allowed_ids']: assert set(case['allowed_ids'])==scoped
    protocol=dict(cases=cases,documents=documents,question_source_sha256=sha(source),
        corpus_sha256=sha(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()),
        model=MODEL,revision=REVISION,dimensions=512,query_prefix=PREFIX,
        bm25=dict(k1=1.2,b=0.75,query_expansion=True),rrf_k=60,candidate_depth=20,
        scope='filter before ranking, negatives restricted to evidence packet N',
        source_code_sha256=sha(Path(__file__).read_bytes()),
        retrieval_code_sha256=sha(Path('backend/app/persisted_hybrid.py').read_bytes()))
    target=Path('data/evals/week04-approved16-protocol.json')
    if target.exists():
        if json.loads(target.read_text(encoding='utf-8'))!=protocol:
            raise ValueError('Frozen protocol differs; create a new version, do not overwrite')
    else:
        target.write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return rows,protocol

def main():
    from sentence_transformers import SentenceTransformer
    rows,protocol=freeze()  # Freeze BEFORE any ranking results.
    started=perf_counter()
    model=SentenceTransformer(MODEL,revision=REVISION,local_files_only=True,device='cpu')
    load_ms=(perf_counter()-started)*1000
    started=perf_counter()
    vectors=model.encode([r['text'] for r in rows],batch_size=8,normalize_embeddings=True)
    index_ms=(perf_counter()-started)*1000
    by_id={r['chunk_id']:v for r,v in zip(rows,vectors)}
    details=[]
    for case in protocol['cases']:
        scoped=scope_rows(rows,case)
        started=perf_counter()
        q=model.encode([PREFIX+case['question']],normalize_embeddings=True)[0]
        encoding_ms=(perf_counter()-started)*1000
        started=perf_counter()
        ranked=sorted(scoped,key=lambda r:(-float(q@by_id[r['chunk_id']]),r['chunk_id']))
        vector_ms=(perf_counter()-started)*1000
        vector_result=dict(items=[dict(chunk_id=r['chunk_id']) for r in ranked[:20]])
        kwargs=dict(company_code=case['company_code'],period=case['period'],top_k=10)
        bm25=hybrid_search(scoped,case['question'],**kwargs)
        rrf=hybrid_search(scoped,case['question'],vector_search=lambda:vector_result,**kwargs)
        for method,result,latency in [('bm25',bm25,bm25['duration_ms']),
            ('vector',vector_result,encoding_ms+vector_ms),('rrf',rrf,encoding_ms+vector_ms+rrf['duration_ms'])]:
            ids=[r['chunk_id'] for r in result['items']][:10]
            scores=score(case['gold_evidence_ids'],ids)
            details.append(dict(case_id=case['id'],method=method,category=case['category'],
                retrieved_ids=ids,**scores,duration_ms=round(latency,3),candidate_count=len(scoped),
                scope_violations=sum(key not in {r['chunk_id'] for r in scoped} for key in ids),
                negative_returned_candidates=bool(ids) if not case['gold_evidence_ids'] else None,
                miss_reason='no_gold_insufficient_evidence' if not case['gold_evidence_ids'] else
                    ('gold_ranked_below_10_or_no_lexical_match' if scores['missing_at_10'] else None)))
    summary={}
    multi_ids={c['id'] for c in protocol['cases'] if len(c['gold_evidence_ids'])>1}
    for method in ('bm25','vector','rrf'):
        group=[r for r in details if r['method']==method]
        positives=[r for r in group if r['recall_at_5'] is not None]
        negatives=[r for r in group if r['recall_at_5'] is None]
        multi=[r for r in group if r['case_id'] in multi_ids]
        times=sorted(r['duration_ms'] for r in group)
        summary[method]=dict(answerable_cases=len(positives),negative_cases=len(negatives),
            recall_at_5=sum(r['recall_at_5'] for r in positives)/len(positives),
            recall_at_10=sum(r['recall_at_10'] for r in positives)/len(positives),
            all_gold_at_5=sum(r['all_gold_at_5'] for r in positives),
            all_gold_at_10=sum(r['all_gold_at_10'] for r in positives),
            multi_evidence_cases=len(multi),multi_all_at_5=sum(r['all_gold_at_5'] for r in multi),
            multi_all_at_10=sum(r['all_gold_at_10'] for r in multi),
            negatives_with_candidates=sum(r['negative_returned_candidates'] for r in negatives),
            scope_violations=sum(r['scope_violations'] for r in group),
            p50_ms=median(times),p95_ms=times[math.ceil(.95*len(times))-1])
    result=dict(protocol_sha256=sha(Path('data/evals/week04-approved16-protocol.json').read_bytes()),
        code_version=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        corpus_chunks=len(rows),model_load_ms=round(load_ms,3),document_encoding_ms=round(index_ms,3),
        timing='local CPU single pass, precomputed document vectors; query encoding included for vector/RRF; no DB/network',
        limitations=['development only; 16 user-reviewed cases; no tuning after protocol freeze',
            'retrieval only: nonempty negative candidates are not supported answers or measured refusal quality',
            'no generalization or production latency claim; official sources not independently verified'],
        summary=summary,details=details)
    Path('data/evals/week04-approved16-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(chunks=len(rows),summary=summary)))

if __name__=='__main__': main()
