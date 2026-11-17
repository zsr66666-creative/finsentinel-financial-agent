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
        assert 'docs/superpowers/specs/2026-11-17-windows-offsite-backup-design.md' in names
        assert 'deploy/windows/install-offsite-task.ps1' in names
        assert 'scripts/windows_offsite_pull.py' in names
        assert not any('google-drive-offsite-backup' in n for n in names)
        assert not any('rclone.conf' in n or n.endswith(('.agekey','.pem','.dump','.pdf','.PDF')) for n in names)


def test_offsite_installer_uses_age_recipient_and_does_not_configure_drive_oauth():
    script=(ROOT/'deploy/ecs/install-operations-offline.sh').read_text(encoding='utf-8')
    assert 'EnvironmentFile=-/etc/finsentinel/offsite-export.env' in script
    assert 'FINSENTINEL_AGE_RECIPIENT' in script
    assert 'rclone' not in script


def test_installer_configures_transactional_read_only_sftp_without_touching_root_keys():
    script=(ROOT/'deploy/ecs/install-operations-offline.sh').read_text(encoding='utf-8')
    assert 'finsentinel-backup-pull' in script
    assert 'ForceCommand internal-sftp -R -d /exports' in script
    assert 'ChrootDirectory /srv/finsentinel-sftp/finsentinel-backup-pull' in script
    assert 'AuthorizedKeysFile /etc/ssh/authorized_keys/%u' in script
    assert 'DisableForwarding yes' in script
    assert 'PermitTTY no' in script
    assert 'AuthenticationMethods publickey' in script
    assert 'sshd -t' in script and 'sshd -T -C user=root' in script
    assert 'ssh_started' in script and 'sshd_config' in script
    assert '/root/.ssh/authorized_keys' not in script
    assert 'FINSENTINEL_AGE_RECIPIENT' in script
    assert 'OFFSITE_ENABLED' not in script


def test_windows_task_setup_is_interactive_daily_and_catches_missed_runs():
    script=(ROOT/'deploy/windows/install-offsite-task.ps1').read_text(encoding='utf-8')
    assert 'New-ScheduledTaskTrigger -Daily' in script
    assert 'New-ScheduledTaskTrigger -AtLogOn' in script
    assert 'New-ScheduledTaskPrincipal' in script and '-LogonType Interactive' in script
    assert '-StartWhenAvailable' in script
    assert 'Register-ScheduledTask' in script and 'FinSentinel-OffsitePull' in script
    assert 'icacls' in script and 'finsentinel-age-key.txt' in script
    assert '$sshKeygen -F $Server -f $knownHostsPath' in script and 'ssh-keyscan' not in script
    assert 'scripts.windows_offsite_pull' in script
    assert 'PRIVATE KEY' not in script and 'rclone config' not in script


def test_offsite_guide_documents_sftp_and_private_key_custody_without_drive_steps():
    guide=(ROOT/'docs/offsite-backup.md').read_text(encoding='utf-8')
    assert 'read-only SFTP' in guide
    assert 'ssh-keyscan' not in guide
    assert '/32' in guide
    assert 'Google Drive' not in guide and 'rclone' not in guide
    assert '离线' in guide
    assert 'Windows' in guide and 'Task Scheduler' in guide
    assert '不能证明 Windows 已拉取' in guide


def test_operations_ui_and_status_contract_do_not_claim_windows_transfer_state():
    page=(ROOT/'frontend/src/app/admin/operations/page.tsx').read_text(encoding='utf-8')
    model=(ROOT/'frontend/src/lib/operations.mjs').read_text(encoding='utf-8')
    assert 'offsite_backup' not in page and 'Google Drive' not in page
    assert 'offsite_backup' not in model
    assert "'offsite_backup'" not in (ROOT/'backend/app/operations.py').read_text(encoding='utf-8')


def test_deployment_prepares_only_test_temp_directory_before_unprivileged_tests():
    script=(ROOT/'deploy/ecs/install-operations-offline.sh').read_text(encoding='utf-8')
    setup='install -d -o finsentinel -g finsentinel -m 700 "$release/.test-tmp-week13"'
    assert setup in script
    assert script.index(setup) < script.index('AUTH_ENABLED=false')
    assert 'chown -R finsentinel:finsentinel "$release"' not in script
