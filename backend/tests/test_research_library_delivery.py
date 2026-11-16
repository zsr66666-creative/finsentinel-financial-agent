from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_installer_preserves_operations_and_migrates_before_cutover():
    s=(ROOT/'deploy/ecs/install-research-library-offline.sh').read_text(encoding='utf-8')
    assert 'scripts.manage_research_library migrate' in s
    assert s.index('scripts.manage_research_library migrate') < s.index('switch_started=1')
    assert '99-zz-research-library.conf' in s
    assert s.index('systemctl start finsentinel-ops-restore.service') < s.index('scripts.manage_research_library migrate')
    assert 'PASS preserved operations; aggregate=' in s
    assert 'systemctl stop finsentinel-ops-' not in s
    assert 'systemctl disable' not in s
    assert 'sites-available' not in s
    assert 'AUTH_COOKIE_SECURE=true' in s
    assert 'install -d -o finsentinel -g finsentinel -m 700 "$release/.test-tmp-week13"' in s
    assert 'sudo -u finsentinel bash -s' in s

def test_smoke_never_creates_production_research_records():
    s=(ROOT/'scripts/research_library_acceptance.py').read_text(encoding='utf-8')
    assert 'POST' not in s
    assert "'/api/v1/me/research/favorites'" in s
    assert "'/my-research'" in s
