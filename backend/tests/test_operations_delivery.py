from pathlib import Path
import hashlib
import tarfile
ROOT=Path(__file__).resolve().parents[2]

def test_deployment_keeps_auth_https_and_first_restore_before_timers():
    script=(ROOT/'deploy/ecs/install-operations-offline.sh').read_text(encoding='utf-8')
    assert 'AUTH_ENABLED=true' in script and 'AUTH_COOKIE_SECURE=true' in script
    assert 'run_ops backup' in script and 'run_ops restore' in script
    assert script.index('run_ops restore') < script.index('systemctl enable --now')
    assert 'rollback_on_exit' in script and 'timer-enabled' in script
    assert 'sites-available' not in script and 'sites-enabled' not in script
    assert 'systemctl stop nginx' not in script
    assert 'root -g root -m 700' in script
    assert 'root -g finsentinel -m 750' in script
    assert 'scripts.manage_accounts check' in script
    assert 'chown -R root:root' in script and 'chmod -R go-w' in script
    assert '/opt/finsentinel-operations-venv/bin/python' in script
    assert script.index('chown -R root:root') < script.index('run_ops backup')
    assert 'WorkingDirectory=$release' in script

def test_status_smoke_is_read_only_and_tls_verified():
    script=(ROOT/'scripts/operations_acceptance.py').read_text(encoding='utf-8')
    assert 'ssl.create_default_context()' in script
    assert 'verify=False' not in script and 'CERT_NONE' not in script
    assert 'POST' not in script
    assert '/admin/operations' in script and '401' in script

def test_committed_package_contains_managed_units_no_production_data(tmp_path):
    from scripts.package_operations import package
    target=tmp_path/'operations.tar.gz';result=package(target)
    assert result['sha256']==hashlib.sha256(target.read_bytes()).hexdigest()
    with tarfile.open(target) as archive:
        names=archive.getnames()
        assert 'deploy/ecs/install-operations-offline.sh' in names
        assert 'backend/app/operations.py' in names
        assert not any(n.endswith(('.dump','.env','.pem','.db','.onnx','.PDF','.pdf')) or 'node_modules' in n or '.next/' in n for n in names)


def test_package_contains_offsite_code_docs_and_spec_without_secrets(tmp_path):
    from scripts.package_operations import package
    target=tmp_path/'operations-offsite.tar.gz';package(target)
    with tarfile.open(target) as archive:
        names=set(archive.getnames())
        assert 'scripts/operations_offsite.py' in names
        assert 'backend/tests/test_operations_offsite.py' in names
        assert 'docs/offsite-backup.md' in names
        assert 'docs/superpowers/specs/2026-11-17-google-drive-offsite-backup-design.md' in names
        assert not any('rclone.conf' in n or n.endswith(('.agekey','.pem','.dump','.pdf','.PDF')) for n in names)


def test_offsite_installer_defaults_disabled_and_keeps_oauth_out_of_env():
    script=(ROOT/'deploy/ecs/install-operations-offline.sh').read_text(encoding='utf-8')
    assert 'EnvironmentFile=-/etc/finsentinel/offsite.env' in script
    assert 'OFFSITE_ENABLED=false' in script
    assert '/etc/rclone/rclone.conf' in script
    assert 'Environment="OFFSITE_TOKEN=' not in script


def test_deployment_prepares_only_test_temp_directory_before_unprivileged_tests():
    script=(ROOT/'deploy/ecs/install-operations-offline.sh').read_text(encoding='utf-8')
    setup='install -d -o finsentinel -g finsentinel -m 700 "$release/.test-tmp-week13"'
    assert setup in script
    assert script.index(setup) < script.index('AUTH_ENABLED=false')
    assert 'chown -R finsentinel:finsentinel "$release"' not in script
