"""Fixed-algorithm cross-document exploratory check, labels pending review."""
import json
from pathlib import Path
from app.exact_metric_experiment import exact_search
from app.persisted_hybrid import hybrid_search
from scripts.week04_approved_eval import sha,score
from scripts.week04_retrieval_comparison import usable

SPECS=[('002241-2024FY','歌尔股份2024年营业规模是多少？',[(8,15)]),
 ('002241-2024FY','歌尔股份2024年经营现金流净额是多少？',[(8,18)]),
 ('002241-2024FY','歌尔股份2024年基本每股收益和稀释每股收益分别是多少？',[(8,19),(8,20)]),
 ('300115-2024FY','长盈精密2024年营业收入是多少？',[(8,10)]),
 ('300115-2024FY','长盈精密2024年经营现金流是多少？',[(8,13)]),
 ('300115-2024FY','长盈精密2024年基本每股收益与稀释每股收益分别是多少？',[(8,14),(8,15)]),
 ('002600-2024FY','领益智造2024年营业规模是多少？',[(10,20)]),
 ('300433-2024FY','蓝思科技2024年营业收入是多少？',[(7,7)])]

def main():
    algorithm=Path('backend/app/exact_metric_experiment.py')
    frozen=json.loads(Path('data/evals/week04-exact-metric-protocol.json').read_text(encoding='utf-8'))
    assert sha(algorithm.read_bytes())==frozen['algorithm_sha256'], 'algorithm changed after development experiment'
    rows=[];documents=[];cases=[]
    for path in sorted(Path('data/derived/documents').glob('*.json')):
        raw=path.read_bytes();doc=json.loads(raw)
        if doc['id'] not in {s[0] for s in SPECS}:continue
        documents.append(dict(id=doc['id'],pdf_sha256=doc['sha256'],json_sha256=sha(raw)))
        for page in doc['pages']:
            explicit=any('合并资产负债表' in s.get('text','') for s in page['spans'])
            for i,span in enumerate(page['spans']):
                content=span.get('text','').strip()
                if not usable(content) or '年度报告全文' in content:continue
                rows.append(dict(chunk_id=f"{doc['id']}-p{page['page']}-s{i}",text=content,
                    company_code=doc['company_code'],period=doc['report_period'],page=page['page'],
                    explicit_consolidated_page=explicit))
    for i,(doc,question,anchors) in enumerate(SPECS,1):
        cases.append(dict(id=f'T{i:02}',question=question,document_id=doc,
            company_code=doc.split('-')[0],period=doc.split('-')[1],
            gold_evidence_ids=[f'{doc}-p{p}-s{s}' for p,s in anchors],
            label_status='assistant_source_checked_pending_human_review'))
    protocol=dict(cases=cases,documents=documents,algorithm_sha256=sha(algorithm.read_bytes()),
        alias_code_sha256=sha(Path('backend/app/metric_query_experiment.py').read_bytes()),
        corpus_sha256=sha(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()),
        script_sha256=sha(Path(__file__).read_bytes()),
        status='exploratory cross-document transfer; NOT independently curated blind test',
        limitations=['same question templates as development','documents may have appeared in historical project data',
                     'no algorithm tuning after results','no negative/table-continuation/negation cases'])
    target=Path('data/evals/week04-transfer-protocol.json')
    if target.exists() and json.loads(target.read_text(encoding='utf-8'))!=protocol:
        raise ValueError('frozen transfer protocol changed')
    target.write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    details=[]
    review=['# 跨文档迁移检查：8题待人工复核\n','此为助手选题的新文档检查，不是盲测；算法保持不变。\n']
    for case in cases:
        scoped=[r for r in rows if r['company_code']==case['company_code'] and r['period']==case['period']]
        by_id={r['chunk_id']:r for r in scoped}
        assert set(case['gold_evidence_ids'])<=set(by_id)
        review.append(f"## {case['id']} {case['question']}\n\n文件：{case['document_id']} 对应年度报告。\n")
        for key in case['gold_evidence_ids']:
            r=by_id[key];review.append(f"- PDF物理页{r['page']}，锚点 `{key}`：\n\n```text\n{r['text']}\n```\n")
        for name,call in [('baseline_bm25',hybrid_search),('fixed_exact_metric',exact_search)]:
            result=call(scoped,case['question'],company_code=case['company_code'],period=case['period'],top_k=10)
            ids=[r['chunk_id'] for r in result['items']]
            details.append(dict(case_id=case['id'],method=name,retrieved_ids=ids,**score(case['gold_evidence_ids'],ids),
                scope_violations=sum(key not in by_id for key in ids)))
    summary={}
    for name in ['baseline_bm25','fixed_exact_metric']:
        group=[r for r in details if r['method']==name]
        summary[name]=dict(cases=len(group),recall_at_5=sum(r['recall_at_5'] for r in group)/len(group),
            recall_at_10=sum(r['recall_at_10'] for r in group)/len(group),
            all_gold_at_5=sum(r['all_gold_at_5'] for r in group),all_gold_at_10=sum(r['all_gold_at_10'] for r in group),
            scope_violations=sum(r['scope_violations'] for r in group))
    Path('data/evals/week04-transfer-results.json').write_text(json.dumps(dict(summary=summary,details=details),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    Path('docs/week04-transfer-review.md').write_text('\n'.join(review),encoding='utf-8')
    print(json.dumps(dict(chunks=len(rows),summary=summary)))

if __name__=='__main__':main()
