"""Read-only trusted TLS report-management acceptance."""
import argparse
import json
from pathlib import Path
import ssl
from scripts.report_reader_acceptance import accept as reader_accept
from scripts.accounts_acceptance import TrustedLocalHTTPS,Assets,IP

def accept():
    report=reader_accept()
    context=ssl.create_default_context()
    def fetch(path,expected):
        c=TrustedLocalHTTPS(IP,timeout=15,context=context)
        try:
            c.request('GET',path);r=c.getresponse();body=r.read()
            if r.status!=expected:raise RuntimeError(f'{path}: expected {expected}, got {r.status}')
            return body
        finally:c.close()
    ident='00000000-0000-4000-8000-000000000000'
    for path in ('/api/v1/me/research/reports','/api/v1/me/research/reports/'+ident,'/api/v1/me/research/reports/'+ident+'/export?format=json'):
        fetch(path,401)
    path='/research-reports/'+ident
    html=fetch(path,200).decode('utf-8');assets=Assets();assets.feed(html)
    if not assets.paths:raise RuntimeError('Report page has no static references')
    for asset in assets.paths:
        if not fetch(asset,200):raise RuntimeError('Empty report page static asset')
    report['checks'].append({'path':path,'status':200,'assets':len(assets.paths)})
    report['limitations'].append('Authenticated save/reopen/export/account isolation require browser acceptance')
    print('PASS saved report shell, assets and anonymous API rejection')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);args=p.parse_args()
    args.output.write_text(json.dumps(accept(),indent=2)+'\n')
