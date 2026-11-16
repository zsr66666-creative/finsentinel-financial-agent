from pathlib import Path
import pytest
from scripts.ip_https import render_http, render_https, ConfigError, ACME_LOCATION

IP='120.24.108.60'
SOURCE='''# keep this site
server {
    listen 80;
    listen [::]:80;
    server_name 120.24.108.60;
    client_max_body_size 20m;
    # braces in comments { } must not affect parsing
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location = /health { proxy_pass http://127.0.0.1:8000; }
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Frame-Options "SAMEORIGIN";
    }
}
'''


def test_http_challenge_preserves_app_and_is_idempotent():
    http=render_http(SOURCE,IP)
    assert http.count('location ^~ /.well-known/acme-challenge/')==1
    assert SOURCE.replace('server {','server {'+ACME_LOCATION,1)==http
    assert render_http(http,IP)==http
    assert 'return 301' not in http and 'listen 443' not in http


def test_https_clones_existing_routes_and_only_replaces_listeners():
    http=render_http(SOURCE,IP);both=render_https(http,IP)
    assert both.startswith(http)
    assert both.count('proxy_pass http://127.0.0.1:8000;')==4
    assert both.count('proxy_pass http://127.0.0.1:3000;')==2
    assert 'listen 443 ssl;' in both and 'listen [::]:443 ssl;' in both
    assert 'ssl_certificate /etc/letsencrypt/live/finsentinel-ip/fullchain.pem;' in both
    assert 'ssl_certificate_key /etc/letsencrypt/live/finsentinel-ip/privkey.pem;' in both
    assert 'staging' not in both and 'ssl_protocols TLSv1.2 TLSv1.3;' in both
    assert render_https(both,IP)==both
    assert render_http(both,IP)==http


@pytest.mark.parametrize('source',[
    SOURCE+SOURCE,
    SOURCE.replace('listen 80;','listen 8080;'),
    SOURCE.replace('listen 80;','listen 80 ssl;'),
    SOURCE.replace('server_name 120.24.108.60;','server_name other.example;'),
    SOURCE.replace('client_max_body_size 20m;','include /etc/nginx/other.conf;'),
    SOURCE.replace('client_max_body_size 20m;','ssl_certificate /tmp/old.pem;'),
    SOURCE[:-3],
    SOURCE.replace('location / {','location /.well-known/acme-challenge/ {'),
    SOURCE.replace('server {','http { server {')+'}',
])
def test_unsupported_nginx_is_refused_before_replacement(source):
    with pytest.raises(ConfigError):render_http(source,IP)


@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.1','120.24.108.60; bad','example.com','::1'])
def test_only_public_ipv4_is_accepted(ip):
    with pytest.raises(ConfigError):render_http(SOURCE,ip)


def test_quoted_braces_comments_and_variables_do_not_break_structure():
    source=SOURCE.replace('client_max_body_size 20m;', 'client_max_body_size 20m;\n    add_header X-Template "${host}:{};#";')
    result=render_https(source,IP)
    assert result.count('add_header X-Template "${host}:{};#";')==2


def test_tls_connect_uses_loopback_but_verifies_public_ip(monkeypatch):
    from scripts import ip_https
    import ssl
    calls = []
    class Raw:
        def close(self): calls.append('closed')
    raw = Raw()
    def connect(address, timeout):
        calls.append(address)
        return raw
    context = ssl.create_default_context()
    def wrap(sock, server_hostname):
        assert sock is raw
        calls.append(server_hostname)
        raise ssl.SSLCertVerificationError('untrusted or wrong IP')
    monkeypatch.setattr(ip_https.socket, 'create_connection', connect)
    monkeypatch.setattr(context, 'wrap_socket', wrap)
    connection = ip_https.LoopbackHTTPS(IP, context=context)
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    with pytest.raises(ssl.SSLCertVerificationError): connection.connect()
    assert calls == [('127.0.0.1', 443), IP, 'closed']


def test_modified_managed_tls_suffix_is_not_silently_overwritten():
    managed = render_https(SOURCE, IP)
    with pytest.raises(ConfigError):
        render_http(managed.replace('TLSv1.2 TLSv1.3', 'TLSv1'), IP)
