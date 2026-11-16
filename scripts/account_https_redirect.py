"""Upgrade the known IP TLS site to redirect application HTTP, preserving HTTP-01."""
import argparse
from pathlib import Path
from scripts.ip_https import ACME_LOCATION, BEGIN, END, ConfigError, parse, render_http

MARKER = '# FINSENTINEL ACCOUNT HTTPS REDIRECT\n'


def canonical(ipv6):
    listeners = '    listen 80;\n' + ('    listen [::]:80;\n' if ipv6 else '')
    return (MARKER + 'server {\n' + listeners + '    server_name 120.24.108.60;\n' +
            ACME_LOCATION + '\n    location / { return 308 https://120.24.108.60$request_uri; }\n}\n')


def redirect_http(source):
    if BEGIN not in source or not source.endswith(END):
        raise ConfigError('Expected the validated FinSentinel IP HTTPS site')
    http, tls = source.split(BEGIN)
    if MARKER in http:
        if http not in (canonical(False), canonical(True)):
            raise ConfigError('Managed HTTP redirect was modified')
        return source
    original_http = render_http(source, '120.24.108.60')
    _, _, listeners = parse(original_http, '120.24.108.60')
    return canonical(any(parts[1][0] == '[::]:80' for parts in listeners)) + BEGIN + tls


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.write_text(redirect_http(args.source.read_text()))
