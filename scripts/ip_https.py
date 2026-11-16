"""Conservative Nginx IP TLS configuration and trusted local acceptance checks."""
import argparse
import http.client
import ipaddress
import re
import socket
import ssl
import time
from pathlib import Path


class ConfigError(ValueError):
    pass


ACME_LOCATION = '''
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/finsentinel-acme;
        default_type text/plain;
        try_files $uri =404;
    }
'''
BEGIN = '# BEGIN FINSENTINEL MANAGED IP HTTPS\n'
END = '# END FINSENTINEL MANAGED IP HTTPS\n'


def public_ip(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ConfigError('Expected public IPv4') from exc
    if address.version != 4 or not address.is_global or str(address) != value:
        raise ConfigError('Expected canonical public IPv4')
    return value


def tokens(source):
    """Yield (raw token, start, end), ignoring comments and quoted punctuation."""
    i = 0
    while i < len(source):
        if source[i].isspace():
            i += 1
            continue
        if source[i] == '#':
            end = source.find('\n', i)
            i = len(source) if end < 0 else end + 1
            continue
        start = i
        if source[i] in '{};':
            i += 1
        else:
            while i < len(source) and not source[i].isspace() and source[i] not in '{};#':
                if source[i] in '\"\'':
                    quote = source[i]
                    i += 1
                    while i < len(source) and source[i] != quote:
                        i += 2 if source[i] == '\\' else 1
                    if i >= len(source):
                        raise ConfigError('Unterminated quote')
                    i += 1
                elif source.startswith('${', i):
                    end = source.find('}', i + 2)
                    if end < 0:
                        raise ConfigError('Unterminated variable')
                    i = end + 1
                elif source[i] == '\\':
                    i += 2
                else:
                    i += 1
        yield source[start:i], start, i


def parse(source, ip):
    public_ip(ip)
    ts = list(tokens(source))
    if len(ts) < 4 or [t[0] for t in ts[:2]] != ['server', '{']:
        raise ConfigError('Expected exactly one standalone HTTP server')
    depth, directives, pending = 1, [], []
    for index, token in enumerate(ts[2:], 2):
        value = token[0]
        if value == '{':
            if depth == 1:
                directives.append((pending, '{'))
                pending = []
            depth += 1
        elif value == '}':
            depth -= 1
            if depth < 0 or (depth == 0 and (index != len(ts) - 1 or pending)):
                raise ConfigError('Multiple/malformed server blocks')
        elif depth == 1:
            if value == ';':
                if not pending:
                    raise ConfigError('Empty directive')
                directives.append((pending + [token], ';'))
                pending = []
            else:
                pending.append(token)
        if value == 'include' or value.startswith('ssl_'):
            raise ConfigError('Includes or existing TLS require manual inspection')
    if depth != 0:
        raise ConfigError('Unbalanced configuration')
    listeners, names = [], []
    for parts, ending in directives:
        values = [p[0] for p in parts]
        if not values:
            raise ConfigError('Malformed block')
        if values[0] == 'listen':
            if ending != ';' or len(values) not in (3, 4) or (len(values) == 4 and values[2] != 'default_server'):
                raise ConfigError('Unsupported listener options')
            if values[1] not in ('80', '[::]:80', '0.0.0.0:80', ip + ':80'):
                raise ConfigError('Expected only HTTP port 80')
            listeners.append(parts)
        elif values[0] == 'server_name':
            names.append(values)
    if not listeners or names != [['server_name', ip, ';']]:
        raise ConfigError('Expected exact public IP server_name and HTTP listener')
    return ts[1][2], ts[-1][1], listeners


def render_http(source, ip):
    if BEGIN in source or END in source:
        if source.count(BEGIN) != 1 or source.count(END) != 1 or not source.endswith(END):
            raise ConfigError('Malformed managed HTTPS suffix')
        original, suffix = source.split(BEGIN)
        if render_https(original, ip) != source:
            raise ConfigError('Managed HTTPS block was modified')
        source = original
    opening, _, _ = parse(source, ip)
    if '.well-known/acme-challenge' in source:
        if source.count('.well-known/acme-challenge') != 1 or ACME_LOCATION not in source:
            raise ConfigError('Existing custom challenge route requires inspection')
        return source
    return source[:opening] + ACME_LOCATION + source[opening:]


def render_https(source, ip):
    if BEGIN in source:
        source = render_http(source, ip)
    http = render_http(source, ip)
    opening, closing, listeners = parse(http, ip)
    body = http[opening:closing]
    for parts in reversed(listeners):
        address = '[::]:443' if parts[1][0] == '[::]:80' else '443'
        body = body[:parts[0][1]-opening] + f'listen {address} ssl;' + body[parts[-1][2]-opening:]
    tls = '''
    ssl_certificate /etc/letsencrypt/live/finsentinel-ip/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/finsentinel-ip/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
'''
    return http + BEGIN + 'server {' + tls + body + '}\n' + END


class LoopbackHTTPS(http.client.HTTPSConnection):
    """Connect locally, validating the real public IP SAN with system CA trust."""
    def connect(self):
        sock = socket.create_connection(('127.0.0.1', 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def smoke(ip):
    public_ip(ip)
    context = ssl.create_default_context()
    for path in ('/health', '/api/v1/evidence/scopes', '/', '/compare', '/login', '/settings', '/companies/002475'):
        connection = LoopbackHTTPS(ip, timeout=15, context=context)
        try:
            connection.request('GET', path)
            response = connection.getresponse()
            data = response.read()
            if response.status != 200:
                raise RuntimeError(f'HTTPS {path}: HTTP {response.status}')
            cert = connection.sock.getpeercert() if connection.sock else None
            # Some HTTP responses close the socket; validate certificate on a separate connection.
            if cert is None:
                connection.connect()
                cert = connection.sock.getpeercert()
            if ssl.cert_time_to_seconds(cert['notAfter']) - time.time() < 86400:
                raise RuntimeError('Certificate expires within 24 hours')
            if path == '/health':
                import json
                if json.loads(data).get('status') != 'ok':
                    raise RuntimeError('Backend health is not ok')
            assets = set(re.findall(r'(?:src|href)=["\'](/_next/static/[^"\']+)', data.decode()))
        finally:
            connection.close()
        for asset in assets:
            check = LoopbackHTTPS(ip, timeout=15, context=context)
            try:
                check.request('GET', asset)
                result = check.getresponse()
                result.read()
                if result.status != 200:
                    raise RuntimeError(f'Static asset HTTP {result.status}: {asset}')
            finally:
                check.close()
        print(f'PASS trusted HTTPS {path}; {len(assets)} static assets')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('http', 'https', 'smoke'))
    parser.add_argument('--ip', required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.mode == 'smoke':
        smoke(args.ip)
    else:
        rendered = (render_http if args.mode == 'http' else render_https)(args.source.read_text(), args.ip)
        args.output.write_text(rendered)


if __name__ == '__main__':
    main()
