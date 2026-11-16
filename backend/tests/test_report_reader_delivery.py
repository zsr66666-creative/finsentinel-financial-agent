from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_reader_installer_preserves_private_research_and_operations():
    s=(ROOT/'deploy/ecs/install-report-reader-offline.sh').read_text(encoding='utf-8')
    assert '99-zzz-report-reader.conf' in s
    assert 'scripts.manage_research_library check' in s
    assert 'scripts.manage_research_library migrate' not in s
    assert s.index('systemctl start finsentinel-ops-restore.service') < s.index('switch_started=1')
    assert 'systemctl disable' not in s
    assert 'PASS preserved operations' in s
    assert 'AUTH_COOKIE_SECURE=true' in s

def test_reader_smoke_is_readonly_and_trusted_tls():
    s=(ROOT/'scripts/report_reader_acceptance.py').read_text(encoding='utf-8')
    assert 'ssl.create_default_context()' in s
    assert 'POST' not in s
    assert "'/reader'" in s
    assert '/api/v1/evidence/reader' in s
