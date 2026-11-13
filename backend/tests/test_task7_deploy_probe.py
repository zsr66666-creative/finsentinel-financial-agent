"""Exercise the actual embedded deploy probe against a login-gated SSR shell."""
import io
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'deploy/ecs/deploy-task7.sh'


class Task7DeployProbeTests(unittest.TestCase):
    def run_probe(self, *, title='FinSentinel', missing_asset=False):
        source = SCRIPT.read_text(encoding='utf-8').rsplit("python3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        html = (f'<html><head><title>{title}</title></head><body>'
                '<div class="session-loading" role="status">正在打开研究工作台…</div>'
                '<script src="/_next/static/chunks/app/compare/page-test.js"></script>'
                '</body></html>').encode()

        class Opener:
            def open(self, request, timeout):
                asset = '/_next/' in request.full_url
                if asset and missing_asset:
                    raise HTTPError(request.full_url, 404, 'missing', {}, None)
                response = io.BytesIO(b'console.log("bundle")' if asset else html)
                response.status = 200
                return response

        with patch('urllib.request.build_opener', return_value=Opener()), patch('time.sleep'), patch('builtins.print'):
            exec(compile(source, str(SCRIPT), 'exec'), {})

    def test_login_shell_does_not_require_client_only_heading(self):
        self.run_probe()

    def test_missing_static_asset_still_fails_acceptance(self):
        with self.assertRaises(HTTPError):
            self.run_probe(missing_asset=True)

    def test_wrong_application_shell_still_fails_acceptance(self):
        with self.assertRaises(RuntimeError):
            self.run_probe(title='Other application')


if __name__ == '__main__':
    unittest.main()
