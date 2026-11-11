"""New development ablation. Does not overwrite approved16 baseline files."""
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from app.metric_query_experiment import plan_queries,balanced_search
from app.persisted_hybrid import hybrid_search
from app.retrieval import reciprocal_rank_fusion
from scripts.week04_approved_eval import freeze,scope_rows,score,sha

def main():
    rows,protocol=freeze()
    old_path=Path('data/evals/week04-approved16-results.json')
    old=json.loads(old_path.read_text(encoding='utf-8'))
    assert old['protocol_sha256']==sha(Path('data/evals/week04-approved16-protocol.json').read_bytes())
    config=dict(base_protocol_sha256=old['protocol_sha256'],baseline_results_sha256=sha(old_path.read_bytes()),
        query_code_sha256=sha(Path('backend/app/metric_query_experiment.py').read_bytes()),
        script_sha256=sha(Path(__file__).read_bytes()),candidate_depth=20,rrf_k=60,
        design='alias rewrite vs metric round-robin; same corpus and scope; unchanged original-query vector ranking',
        status='development tuning after observing approved16 failures, NOT independent validation')
    dest=Path('data/evals/week04-query-ablation-protocol.json')
    if dest.exists() and json.loads(dest.read_text(encoding='utf-8'))!=config:
        raise ValueError('ablation protocol changed; create new experiment version')
    dest.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    details=[]
    for case in protocol['cases']:
        scoped=scope_rows(rows,case)
        kwargs=dict(company_code=case['company_code'],period=case['period'],top_k=20)
        queries=plan_queries(case['question'])
        rewritten=' '.join(queries) if queries else case['question']
        lexical=hybrid_search(scoped,rewritten,**kwargs)
        balanced=balanced_search(scoped,case['question'],**kwargs)
        vector=next(r for r in old['details'] if r['case_id']==case['id'] and r['method']=='vector')
        # Published baseline saves Top-10 only. Explicitly freeze fusion depth
        # to 10 for BOTH arms here; do not pretend this is the former depth-20 RRF.
        started=perf_counter()
        fused=reciprocal_rank_fusion([[r['chunk_id'] for r in balanced['items'][:10]],vector['retrieved_ids'][:10]])
        fusion_ms=(perf_counter()-started)*1000
        for method,ids,latency in [
            ('alias_bm25',[r['chunk_id'] for r in lexical['items']][:10],lexical['duration_ms']),
            ('balanced_bm25',[r['chunk_id'] for r in balanced['items']][:10],balanced['duration_ms']),
            ('balanced_rrf_depth10',[key for key,s in fused][:10],balanced['duration_ms']+fusion_ms)]:
            metrics=score(case['gold_evidence_ids'],ids)
            details.append(dict(case_id=case['id'],method=method,queries=queries,retrieved_ids=ids,**metrics,
                duration_ms=round(latency,3),scope_violations=sum(key not in {r['chunk_id'] for r in scoped} for key in ids)))
    summary={}
    for method in ('alias_bm25','balanced_bm25','balanced_rrf_depth10'):
        group=[r for r in details if r['method']==method]
        positive=[r for r in group if r['recall_at_5'] is not None]
        multi_ids={c['id'] for c in protocol['cases'] if len(c['gold_evidence_ids'])>1}
        multi=[r for r in positive if r['case_id'] in multi_ids]
        summary[method]=dict(recall_at_5=sum(r['recall_at_5'] for r in positive)/len(positive),
            recall_at_10=sum(r['recall_at_10'] for r in positive)/len(positive),
            all_gold_at_5=sum(r['all_gold_at_5'] for r in positive),
            all_gold_at_10=sum(r['all_gold_at_10'] for r in positive),answerable_cases=len(positive),
            multi_all_at_5=sum(r['all_gold_at_5'] for r in multi),
            multi_all_at_10=sum(r['all_gold_at_10'] for r in multi),multi_cases=len(multi),
            negative_candidates=sum(bool(r['retrieved_ids']) for r in group if r['recall_at_5'] is None),
            scope_violations=sum(r['scope_violations'] for r in group),
            p50_stage_ms=median(r['duration_ms'] for r in group))
    result=dict(protocol=config,summary=summary,details=details,
        limitations=['development tuning, not generalization','RRF uses cached baseline Top-10 vector IDs, not live vector retrieval',
        'stage timing excludes query encoding/vector search; not comparable with baseline end-to-end timing',
        'four negative cases do not measure answer/refusal quality; no production changes'])
    Path('data/evals/week04-query-ablation-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))

if __name__=='__main__': main()
