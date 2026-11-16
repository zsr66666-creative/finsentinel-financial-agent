"""Read-only cloud smoke: trusted TLS, protected API, frontend/static availability.

Authenticated role tests run against an isolated database in test_accounts.py.
This smoke never creates production users, financial decisions or sessions.
"""
import argparse
from html.parser import HTMLParser
import http.client
import json
from pathlib import Path
import socket
import ssl
import time


IP = '120.24.108.60'


class TrustedLocalHTTPS(http.client.HTTPSConnection):
    def connect(self):
        raw = socket.create_connection(('127.0.0.1', 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        path = attrs.get('src') if tag == 'script' else attrs.get('href') if tag == 'link' else None
        if path and path.startswith('/_next/static/') and path.endswith(('.css', '.js')):
            self.paths.add(path)


def smoke(backend_only=False):
    context = ssl.create_default_context()
    records = []

    def fetch(path, expected=200):
        if backend_only:
            connection = http.client.HTTPConnection('127.0.0.1', 8000, timeout=15)
        else:
            connection = TrustedLocalHTTPS(IP, timeout=15, context=context)
        try:
            connection.request('GET', path, headers={'Host': IP})
            response = connection.getresponse()
            data = response.read()
            if response.status != expected:
                raise RuntimeError(f'{path}: expected {expected}, got {response.status}')
            return data
        finally:
            connection.close()

    for attempt in range(25):
        try:
            value = json.loads(fetch('/health'))
            if value.get('status') != 'ok':
                raise RuntimeError('Backend not healthy')
            break
        except Exception:
            if attempt == 24:
                raise
            time.sleep(2)
    for path in ('/api/v1/auth/session', '/api/v1/companies', '/api/v1/evidence/scopes',
                 '/api/v1/auth/users', '/api/v1/companies/002555/financial-reviews'):
        fetch(path, 401)
        records.append({'path': path, 'status': 401})
        print(f'PASS anonymous access denied: {path}')
    if not backend_only:
        for path in ('/login', '/api/v1/auth/login'):
            plain = http.client.HTTPConnection('127.0.0.1', 80, timeout=15)
            try:
                plain.request('GET', path, headers={'Host': IP})
                response = plain.getresponse()
                response.read()
                if response.status != 308 or response.getheader('Location') != f'https://{IP}{path}':
                    raise RuntimeError(f'HTTP credential route did not redirect: {path}')
                print(f'PASS HTTP to HTTPS redirect: {path}')
            finally:
                plain.close()
        # systemctl start returns before Node accepts connections.
        for attempt in range(25):
            try:
                if 'FinSentinel' not in fetch('/login').decode('utf-8'):
                    raise RuntimeError('Frontend shell not ready')
                break
            except Exception:
                if attempt == 24:
                    raise
                time.sleep(2)
        paths = ('/', '/login', '/settings', '/compare', '/companies', '/reports', '/evidence',
                 '/companies/002475', '/companies/002555', '/companies/002230',
                 '/workbench', '/workbench/alerts', '/workbench/review', '/workbench/evals', '/workbench/data',
                 '/admin/users')
        for path in paths:
            html = fetch(path).decode('utf-8')
            if 'FinSentinel' not in html:
                raise RuntimeError(f'{path}: missing application shell')
            parser = Assets()
            parser.feed(html)
            if not parser.paths:
                raise RuntimeError(f'{path}: missing CSS/JS references')
            for asset in parser.paths:
                if not fetch(asset):
                    raise RuntimeError(f'Empty asset: {asset}')
            records.append({'path': path, 'status': 200, 'assets': len(parser.paths)})
            print(f'PASS trusted HTTPS {path}; {len(parser.paths)} assets')
    return {'status': 'passed', 'checks': records,
            'limitations': ['read-only smoke; authenticated role and interactive browser acceptance remain separate']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend-only', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(smoke(args.backend_only), indent=2)+'\n')
