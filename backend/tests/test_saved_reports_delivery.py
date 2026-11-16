from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_saved_reports_deployment_backup_before_explicit_migration():
    script=(ROOT/'deploy/ecs/install-saved-reports-offline.sh').read_text(encoding='utf-8')
    assert script.index('systemctl start finsentinel-ops-restore.service') < script.index('scripts.manage_saved_reports migrate') < script.index('switch_started=1')
    assert '99-zzzz-saved-reports.conf' in script
    assert 'scripts.manage_saved_reports check' in script
    assert 'scripts.manage_research_library check' in script
    assert 'AUTH_COOKIE_SECURE=true' in script
    assert 'systemctl disable' not in script

def test_saved_reports_smoke_preserves_authenticated_reader():
    script=(ROOT/'scripts/saved_reports_acceptance.py').read_text(encoding='utf-8')
    assert 'report_reader_acceptance import accept' in script
    assert '/api/v1/me/research/reports' in script
    assert 'ssl.create_default_context()' in script
    assert "'/research-reports/" in script
