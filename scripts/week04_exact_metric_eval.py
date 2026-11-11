"""Separate development run, immutable prior results, no model or DB writes."""
import json
from pathlib import Path
from app.exact_metric_experiment import exact_search
from scripts.week04_approved_eval import freeze,scope_rows,score,sha

def main():
    rows,protocol=freeze()
    explicit=set()
    for path in Path('data/derived/documents').glob('*.json'):
        doc=json.loads(path.read_text(encoding='utf-8'))
        for page in doc['pages']:
            if any('合并资产负债表' in s.get('text','') for s in page.get('spans',[])):
                explicit.add((doc['id'],page['page']))
    for row in rows:
        document=row['chunk_id'].split('-p')[0]
        row['explicit_consolidated_page']=(document,row['page']) in explicit
    config=dict(base_protocol_sha256=sha(Path('data/evals/week04-approved16-protocol.json').read_bytes()),
        algorithm_sha256=sha(Path('backend/app/exact_metric_experiment.py').read_bytes()),
        script_sha256=sha(Path(__file__).read_bytes()),
        rule='exact numeric row label; explicit same-page consolidated balance-sheet title; round-robin then lexical fallback',
        scope='same corpus and negative allowlist; development tuning, not held-out validation')
    path=Path('data/evals/week04-exact-metric-protocol.json')
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:
        raise ValueError('protocol changed; use another version')
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    details=[]
    for case in protocol['cases']:
        scoped=scope_rows(rows,case)
        result=exact_search(scoped,case['question'],company_code=case['company_code'],period=case['period'],top_k=10)
        ids=[r['chunk_id'] for r in result['items']]
        details.append(dict(case_id=case['id'],retrieved_ids=ids,**score(case['gold_evidence_ids'],ids),
            queries=result['queries'],duration_ms=result['duration_ms'],
            scope_violations=sum(key not in {r['chunk_id'] for r in scoped} for key in ids)))
    positives=[r for r in details if r['recall_at_5'] is not None]
    multi_ids={c['id'] for c in protocol['cases'] if len(c['gold_evidence_ids'])>1}
    summary=dict(answerable_cases=len(positives),
        recall_at_5=sum(r['recall_at_5'] for r in positives)/len(positives),
        recall_at_10=sum(r['recall_at_10'] for r in positives)/len(positives),
        all_gold_at_5=sum(r['all_gold_at_5'] for r in positives),
        all_gold_at_10=sum(r['all_gold_at_10'] for r in positives),
        multi_all_at_5=sum(r['all_gold_at_5'] for r in positives if r['case_id'] in multi_ids),
        multi_cases=len(multi_ids),negative_candidates=sum(bool(r['retrieved_ids']) for r in details if r['recall_at_5'] is None),
        scope_violations=sum(r['scope_violations'] for r in details))
    Path('data/evals/week04-exact-metric-results.json').write_text(json.dumps(dict(protocol=config,summary=summary,details=details),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))

if __name__=='__main__':main()
