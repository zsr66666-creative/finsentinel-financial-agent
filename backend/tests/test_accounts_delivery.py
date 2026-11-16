"""Delivery invariants for account mode, without changing production data."""
from pathlib import Path
import io
import tarfile
import hashlib

ROOT=Path(__file__).resolve().parents[2]

def test_installer_enables_server_auth_and_never_disables_tls():
    source=(ROOT/'deploy/ecs/install-accounts-offline.sh').read_text()
    assert 'AUTH_ENABLED=true' in source
    assert 'AUTH_ORIGIN=https://120.24.108.60' in source
    assert 'AUTH_COOKIE_SECURE=true' in source
    assert 'scripts.manage_accounts bootstrap' in source
    assert source.index('scripts.manage_accounts bootstrap') < source.index('switch_started=1')
    assert 'pg_dump -Fc' in source and 'rollback_on_exit' in source
    assert 'nginx -t' in source
    assert 'scripts.account_https_redirect' in source
    assert 'backup/nginx.conf' in source and 'certbot renew' in source
    assert 'systemctl stop nginx' not in source
    assert '--forwarded-allow-ips 127.0.0.1' in source
    assert 'scripts.accounts_acceptance' in source
    assert 'financial-review.env' not in source
    assert 'Pillow==' in source


def test_accounts_smoke_refuses_tls_bypass_and_production_fake_reviews():
    source=(ROOT/'scripts/accounts_acceptance.py').read_text()
    assert 'ssl.create_default_context()' in source
    assert 'CERT_NONE' not in source and 'verify=False' not in source
    assert '401' in source and '/api/v1/auth/session' in source
    assert '.post(' not in source


def test_package_source_only_and_manifest_matches(tmp_path):
    from scripts.package_accounts import package
    output=tmp_path/'accounts.tar.gz'
    report=package(output)
    assert report['sha256']==hashlib.sha256(output.read_bytes()).hexdigest()
    with tarfile.open(output) as archive:
        names=archive.getnames()
        assert 'deploy/ecs/install-accounts-offline.sh' in names
        assert 'backend/app/auth/routes.py' in names
        assert not any('.next/' in n or 'node_modules' in n or n.endswith(('.env','.db','.pem','.onnx')) for n in names)
