import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fetch = load('official_fetch')
check = load('audit_candidates')
SCOPE = json.loads((ROOT / 'examples/research_scope.json').read_text(encoding='utf8'))
ROW = json.loads((ROOT / 'examples/candidate.json').read_text(encoding='utf8'))[0]
HTML = ('<a href="/UploadFiles/jrlf/2026/6/202606041647452973.pdf">'
        '廊坊市2025年国民经济和社会发展统计公报</a>'
        '<a href="javascript:void(0)">导航</a>').encode('utf8')


class SkillTests(unittest.TestCase):
    def test_original_negative_and_next_year_edition(self):
        self.assertTrue(check.audit([ROW], SCOPE)['all_passed'])

    def test_unverified_or_derived_rejected(self):
        for change in [{'scope_verified': False}, {'is_derived': True}, {'official_verified': False}, {'value_verified': False}]:
            self.assertFalse(check.audit([dict(ROW, **change)], SCOPE)['all_passed'])

    def test_invalid_values_or_out_of_scope_rejected(self):
        for change in [{'value': float('nan')}, {'value': True}, {'indicator': '新增就业人数'}, {'year': 2026}, {'edition': 2024}]:
            self.assertFalse(check.audit([dict(ROW, **change)], SCOPE)['all_passed'])

    def test_mixed_batch_does_not_pass(self):
        r = check.audit([ROW, dict(ROW, scope_verified=False)], SCOPE)
        self.assertEqual((r['passed'], r['failed'], r['all_passed']), (1, 1, False))

    def test_exact_hosts_and_redirects(self):
        hosts = {'www.lf.gov.cn': {'publisher': 'test'}}
        fetch.check_url(ROW['url'], hosts)
        for url in ['https://www.lf.gov.cn.evil.invalid/a', 'https://unknown.lf.gov.cn/a', 'file:///tmp/x', 'https://u:p@www.lf.gov.cn/a']:
            with self.assertRaises(ValueError):
                fetch.check_url(url, hosts)
        with self.assertRaises(ValueError):
            fetch.CheckedRedirect(hosts).redirect_request(None, None, 302, '', {}, 'https://example.com/x')

    def test_catalog_attachment_resolution(self):
        links = fetch.inspect_html(HTML, ROW['publication_url'])
        self.assertTrue(any(r['url'] == ROW['url'] and r['is_attachment'] for r in links))
        self.assertFalse(any(r['url'].startswith('javascript:') for r in links))

    def test_cache_reuse_and_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            html = base / 'catalog.html'
            html.write_bytes(HTML)
            args = SimpleNamespace(registry=str(ROOT / 'examples/official_hosts.json'), url=ROW['publication_url'], output=str(base / 'cache'), refresh=False, html=str(html), max_bytes=1000000, encoding=None, retries=0, timeout=25)
            r = fetch.fetch(args)
            key = fetch.hashlib.sha256(args.url.encode()).hexdigest()[:24]
            fetch.write_json(base / 'cache' / (key + '.json'), dict(r, mode='network'))
            args.html = None
            with patch.object(fetch.urllib.request, 'build_opener', side_effect=AssertionError('No network expected')):
                self.assertTrue(fetch.fetch(args)['cache_hit'])
            (base / 'cache' / r['file']).write_bytes(b'changed')
            with self.assertRaises(ValueError):
                fetch.fetch(args)


if __name__ == '__main__':
    unittest.main()
