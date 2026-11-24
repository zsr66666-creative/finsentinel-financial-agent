"""Check whether the five pilot companies have verified adjacent-year inputs."""

import os
import sys

from fastapi.testclient import TestClient

from app.corpus import load_corpus
from app.main import create_app


PILOTS = [
    ('000100', 'TCL科技'), ('000157', '中联重科'), ('000425', '徐工机械'),
    ('000528', '柳工'), ('000725', '京东方A'),
]


def main():
    app = create_app(database_url='sqlite://', data_mode='empty')
    corpus_path = os.getenv('CORPUS_PATH')
    if corpus_path:
        load_corpus(app.state.store, corpus_path)
    for code, name in PILOTS:
        if not app.state.store.get('companies', code):
            app.state.store.put('companies', {'id':code,'code':code,'name':name,'data_mode':'real_corpus'})

    complete = 0
    with TestClient(app) as client:
        for code, name in PILOTS:
            response = client.get(f'/api/v1/companies/{code}/financial-analysis?from_period=2023FY&to_period=2024FY')
            if response.status_code != 200:
                print(f'FAIL {code} {name}: HTTP {response.status_code}')
                continue
            result = response.json()
            if result['status'] == 'completed':
                complete += 1
                print(f'PASS {code} {name}: {result["classification"]}; evidence_pages={len(result["evidence"])}')
            else:
                print(f'NEEDS_REVIEW {code} {name}: {result.get("reason")}')
    print(f'FINANCIAL_ACCEPTANCE={complete}/5')
    return 0 if complete == len(PILOTS) else 2


if __name__ == '__main__':
    sys.exit(main())
