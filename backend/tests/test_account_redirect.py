import pytest
from scripts.account_https_redirect import redirect_http, MARKER
from scripts.ip_https import render_https, ACME_LOCATION, ConfigError

SOURCE='server {\n    listen 80;\n    listen [::]:80;\n    server_name 120.24.108.60;\n    location /api/ { proxy_pass http://127.0.0.1:8000; }\n    location / { proxy_pass http://127.0.0.1:3000; }\n}\n'

def test_redirect_preserves_tls_and_acme_not_http_application():
    original=render_https(SOURCE,'120.24.108.60')
    result=redirect_http(original)
    assert result.startswith(MARKER)
    http,tls=result.split('# BEGIN FINSENTINEL MANAGED IP HTTPS\n')
    assert ACME_LOCATION in http
    assert 'location / { return 308 https://120.24.108.60$request_uri; }' in http
    assert 'proxy_pass' not in http
    assert tls==original.split('# BEGIN FINSENTINEL MANAGED IP HTTPS\n')[1]
    assert redirect_http(result)==result

def test_unknown_or_modified_redirect_is_refused():
    with pytest.raises(ConfigError):redirect_http(SOURCE)
    original=redirect_http(render_https(SOURCE,'120.24.108.60'))
    with pytest.raises(ConfigError):redirect_http(original.replace('return 308','return 301'))
