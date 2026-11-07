import json
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
with TestClient(create_app('sqlite:///:memory:')) as c:
    # Public summary confirms the fixture set; use API-independent seeded data through the app.
    cases=[]
    # derive from known seed metric contract
    for company in c.get('/api/v1/companies').json()['items'][:20]:
        cid=company['id']
        for metric in ('revenue','net_profit'):
            item=c.get(f'/api/v1/companies/{cid}/metrics?period=2025').json()['items']
            row=next((m for m in item if m.get('metric')==metric),None)
            if row:
                cases.append({'id':f'fixture-{cid}-2025-{metric}','question':f'2025 年 {metric} 是多少？','type':'fact_lookup','period':'2025','company_id':cid,'answer':{'value':row['value'],'unit':row.get('unit')},'gold_evidence_ids':row.get('source_ids',[]),'split':'development','annotation_status':'synthetic_fixture_approved','corpus_version':'synthetic-demo-v1'})
Path('data/evals/week14-shared-fixture.jsonl').write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in cases)+'\n',encoding='utf-8')
print('cases',len(cases))
