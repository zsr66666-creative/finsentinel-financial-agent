"""ECS source + HTTP + Task10 regression acceptance for six financial contracts."""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys

import requests
from sqlalchemy import create_engine, text

from app.verified_financials import company_comparisons, DEFAULT_ARTIFACT_ROOT

# Independent acceptance values read from the financial statements, not from the
# runtime manifest; a self-consistent changed contract must fail acceptance.
EXPECTED = {
    '002555': {'revenue':('17440957495.58','16546871737.85','894085757.73','5.40',92),
               'receivables':('1212667677.20','1479267695.67','-266600018.47','-18.02',88),
               'operating_cash_flow':('2997982682.73','3147037336.46','-149054653.73','-4.74',95)},
    '002230': {'revenue':('23343093018.69','19650329209.04','3692763809.65','18.79',119),
               'receivables':('14666453043.92','12165102111.50','2501350932.42','20.56',115),
               'operating_cash_flow':('2495173454.92','349757814.55','2145415640.37','613.40',123)},
}


def verify_result(result, code):
    assert result['company_code'] == code and result['period'] == '2024FY'
    assert result['statement_scope'] == 'consolidated' and result['status'] == 'supported'
    assert result['review_status'] == 'pending_human' and result['data_mode'] == 'source_verified_financial_contract'
    assert result['total'] == len(result['items']) == 3
    assert {m['metric'] for m in result['items']} == set(EXPECTED[code])
    for metric in result['items']:
        expected = EXPECTED[code][metric['metric']]
        assert tuple(metric[k] for k in ('current_value','previous_value','difference','change_percent')) == expected[:4]
        assert next(e['page'] for e in metric['evidence'] if e['role']=='row') == expected[4]
        assert metric['review_status'] == 'pending_human' and metric['status'] == 'supported'
        assert metric['unit']=='CNY' and metric['statement_scope']=='consolidated'
        if metric['metric'] != 'receivables':
            assert metric['period_kind']=='flow'
            assert metric['current_period']=='2024-01-01/2024-12-31' and metric['previous_period']=='2023-01-01/2023-12-31'
            assert metric['current_column']=='2024 年度' and metric['previous_column']=='2023 年度'
        else:
            assert metric['period_kind']=='balance' and metric['current_period']=='2024-12-31'
            assert metric['previous_period']==('2024-01-01' if code=='002230' else 'opening_balance_2024')
            assert metric['current_column']==('2024 年12 月31 日' if code=='002230' else '期末余额')
            assert metric['previous_column']==('2024 年1 月1 日' if code=='002230' else '期初余额')
        assert Decimal(metric['difference']) == Decimal(metric['current_value'])-Decimal(metric['previous_value'])
    if code == '002230':
        assert next(m for m in result['items'] if m['metric']=='receivables')['previous_period']=='2024-01-01'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-url', default='http://127.0.0.1:8000')
    parser.add_argument('--host-header')
    parser.add_argument('--artifact-root', default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    engine = create_engine(os.environ['DATABASE_URL'])
    results = []
    try:
        with engine.connect() as conn:
            before = conn.execute(text('SELECT count(*) FROM document_chunk_embeddings')).scalar_one()
        for code in EXPECTED:
            direct = company_comparisons(engine,code,'2024FY','consolidated',args.artifact_root)
            verify_result(direct,code)
            results.append(direct)
        if not args.source_only:
            session = requests.Session();session.trust_env = False
            if args.host_header:session.headers['Host']=args.host_header
            for code, direct in zip(EXPECTED,results):
                url=args.api_url+'/api/v1/companies/'+code+'/financial-comparison'
                response=session.get(url,timeout=20);response.raise_for_status()
                body=response.json();verify_result(body,code);assert body==direct
                for params in [dict(statement_scope='parent'),dict(period='2023FY')]:
                    rejected=session.get(url,params=params,timeout=20);rejected.raise_for_status()
                    value=rejected.json();assert value['status']=='needs_review' and value['items']==[]
            previous=[sys.executable,'-m','scripts.task10_acceptance','--api-url',args.api_url,
                      '--artifact-root',args.artifact_root,'--output',str(Path(args.output).with_name(Path(args.output).stem+'-task10.json'))]
            if args.host_header:previous+=['--host-header',args.host_header]
            subprocess.run(previous,check=True,timeout=300)
        with engine.connect() as conn:
            after=conn.execute(text('SELECT count(*) FROM document_chunk_embeddings')).scalar_one()
        assert before==after, 'Task11 must not publish or change vector rows'
        result=dict(status='passed',source_only=args.source_only,financial_comparisons=results,
                    embeddings_before=before,embeddings_after=after,
                    task10_regression='not_run_source_only' if args.source_only else 'passed',
                    limitations=['six_fixed_source_contracts_only','pending_independent_human_review','browser_acceptance_separate'])
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(status='passed',companies=list(EXPECTED),metric_count=6,
            source_only=args.source_only,embeddings_before=before,embeddings_after=after),ensure_ascii=False))
    finally:engine.dispose()


if __name__=='__main__':main()
