"""Read-only TLS/page acceptance; authentication boundaries never use production passwords."""
import argparse
import json
from pathlib import Path
import ssl
from scripts.accounts_acceptance import smoke, TrustedLocalHTTPS, Assets, IP


def accept():
    report = smoke()
    context = ssl.create_default_context()

    def fetch(path, expected):
        connection = TrustedLocalHTTPS(IP, timeout=15, context=context)
        try:
            connection.request('GET', path)
            response = connection.getresponse()
            data = response.read()
            if response.status != expected:
                raise RuntimeError(f'{path}: expected {expected}, got {response.status}')
            return data
        finally:
            connection.close()

    fetch('/api/v1/admin/operations', 401)
    html = fetch('/admin/operations', 200).decode('utf-8')
    if 'FinSentinel' not in html:
        raise RuntimeError('Missing operations application shell')
    assets = Assets()
    assets.feed(html)
    if not assets.paths:
        raise RuntimeError('Operations page has no static references')
    for path in assets.paths:
        if not fetch(path, 200):
            raise RuntimeError('Empty operations static asset')
    print('PASS trusted HTTPS /admin/operations and anonymous admin API rejection')
    report['checks'].append({'path': '/admin/operations', 'status': 200, 'assets': len(assets.paths)})
    report['limitations'].append('Authenticated operations page requires administrator browser acceptance')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(accept(), indent=2)+'\n')
