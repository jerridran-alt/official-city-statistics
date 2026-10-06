import copy
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import official_fetch as fetch
from collect_sources import collect
from extract_tables import extract
from audit_candidates import audit
from select_panel import priority, select
from stats_core import number, read_source, save

CONFIG = json.loads((ROOT / 'examples/project.json').read_text(encoding='utf8'))
MAPPING = json.loads((ROOT / 'examples/table_mapping.json').read_text(encoding='utf8'))
REGISTRY = json.loads((ROOT / 'examples/official_hosts.json').read_text(encoding='utf8'))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.html'
        self.source.write_bytes((ROOT / 'examples/sample_table.html').read_bytes())
        self.parsed = read_source(self.source, 'html')
        self.records = extract(self.parsed, MAPPING, CONFIG, self.source, self.root)['records']

    def verify(self, rows=None):
        return audit(self.records if rows is None else rows, CONFIG, self.root, REGISTRY)

    def test_every_city_without_province_total(self):
        self.assertEqual(len(self.records), 6)
        self.assertEqual({r['city'] for r in self.records}, {'廊坊市', '衡水市', '唐山市'})
        self.assertEqual([r['value'] for r in self.records], [100.2, 20.5, 200.3, 30.6, 300.4, 40.7])
        unknown = [r for r in self.records if r['city'] == '唐山市']
        self.assertTrue(all(r['research_id'] is None and r['identity_status'] == 'unmapped' for r in unknown))

    def test_merged_headers(self):
        cells = self.parsed['tables'][0]['cells']
        self.assertEqual(cells[0][1:3], ['2024年', '2024年'])
        self.assertEqual(cells[1][0], '城市')

    def test_thirty_one_city_rows_without_research_list(self):
        text = self.source.read_text(encoding='utf8')
        prefix = text.split('<tr><td>')[0]
        rows = ''.join(f'<tr><td>样例{i}市</td><td>{100 + i}</td><td>{20 + i}</td></tr>' for i in range(31))
        self.source.write_text(prefix + rows + '<tr><td>省合计</td><td>9999</td><td>9999</td></tr></table></body></html>', encoding='utf8')
        config = dict(CONFIG, units=[])
        result = extract(read_source(self.source, 'html'), MAPPING, config, self.source, self.root)
        self.assertEqual((result['source_cities_extracted'], len(result['records'])), (31, 62))
        self.assertEqual(result['research_units_matched'], 0)
        self.assertTrue(all(r['research_id'] is None for r in result['records']))

    def test_original_read_once_and_offline_not_certified(self):
        r = self.verify()
        self.assertTrue(r['machine_checks_passed'])
        self.assertEqual(r['source_files_read'], 1)
        self.assertFalse(any(v['origin']['capture_matched'] for v in r['results']))
        self.assertTrue(all(v['semantic_review_required'] for v in r['results']))

    def test_true_flags_cannot_cover_wrong_number(self):
        rows = copy.deepcopy(self.records)
        rows[0].update(value=999, official_verified=True, value_verified=True, scope_verified=True)
        self.assertFalse(self.verify(rows)['machine_checks_passed'])

    def test_true_flags_without_evidence_rejected(self):
        row = copy.deepcopy(self.records[0])
        row.pop('evidence')
        row.update(official_verified=True, value_verified=True, scope_verified=True)
        self.assertFalse(self.verify([row])['machine_checks_passed'])

    def test_tampered_source(self):
        self.source.write_text(self.source.read_text(encoding='utf8').replace('100.2', '999.9'), encoding='utf8')
        self.assertFalse(self.verify()['machine_checks_passed'])

    def test_wrong_city_unit_or_indicator(self):
        row = copy.deepcopy(self.records[0])
        row['evidence']['city_cell'] = [3, 0]
        self.assertFalse(self.verify([row])['machine_checks_passed'])
        for changes in ({'unit': '万元'}, {'indicator': '全社会用电量'}):
            self.assertFalse(self.verify([dict(self.records[0], **changes)])['machine_checks_passed'])

    def test_duplicate_identity(self):
        self.assertFalse(self.verify([self.records[0], self.records[0]])['machine_checks_passed'])

    def test_path_outside_root(self):
        row = copy.deepcopy(self.records[0])
        row['evidence']['file'] = '../outside.html'
        self.assertFalse(self.verify([row])['machine_checks_passed'])

    def test_inconsistent_header_mapping(self):
        mapping = copy.deepcopy(MAPPING)
        mapping['tables'][0]['columns'][0]['unit'] = '万元'
        r = extract(self.parsed, mapping, CONFIG, self.source, self.root)
        self.assertEqual((len(r['errors']), len(r['records'])), (3, 3))

    def test_literal_zero_negative_missing(self):
        self.assertEqual(number('下降7.2%'), -7.2)
        self.assertEqual(number('0'), 0)
        self.assertEqual(number('1,234.5'), 1234.5)
        for raw in ('', '—', '..', '计划100', '=A1+B1'):
            self.assertIsNone(number(raw))

    def test_cli_table_cache_reuse(self):
        mapping, config = self.root / 'mapping.json', self.root / 'project.json'
        save(mapping, MAPPING)
        save(config, CONFIG)
        cmd = [sys.executable, str(ROOT / 'scripts/extract_tables.py'), '--input', str(self.source), '--format', 'html', '--config', str(config), '--mapping', str(mapping), '--output', str(self.root / 'candidates.json'), '--cache-dir', str(self.root / 'tables'), '--evidence-root', str(self.root)]
        first = subprocess.run(cmd, capture_output=True, text=True, check=True)
        second = subprocess.run(cmd, capture_output=True, text=True, check=True)
        self.assertFalse(json.loads(first.stdout)['source_table_cache_reused'])
        self.assertTrue(json.loads(second.stdout)['source_table_cache_reused'])

    def test_unreviewed_offline_not_selected(self):
        r = select(self.records, CONFIG, self.verify(), [])
        self.assertEqual((len(r['selected']), len(r['pending'])), (0, 4))
        self.assertEqual(len(r['excluded_from_panel']), 2)

    def test_inconsistent_capture_manifest(self):
        row = copy.deepcopy(self.records[0])
        save(self.root / 'capture.json', {'sha256': 'wrong', 'file': self.source.name, 'bytes': self.source.stat().st_size, 'mode': 'network'})
        row['evidence']['capture_manifest'] = 'capture.json'
        self.assertFalse(self.verify([row])['machine_checks_passed'])

    def test_consistent_capture_and_separate_review(self):
        # Synthetic capture fixture tests the consistency contract, not live authenticity.
        path = self.root / 'capture.json'
        save(path, {'sha256': self.parsed['source_sha256'], 'file': self.source.name, 'bytes': self.source.stat().st_size, 'mode': 'network', 'final_url': 'https://www.lf.gov.cn/example-fixture', 'publisher': '廊坊市人民政府'})
        rows = extract(self.parsed, MAPPING, CONFIG, self.source, self.root, path)['records']
        report = self.verify(rows)
        self.assertTrue(all(v['origin']['capture_matched'] for v in report['results']))
        reviews = [{'record_id': r['id'], 'source_sha256': r['evidence']['sha256'], 'decision': 'approve', 'reviewer': 'test-fixture-reviewer', 'reason': 'synthetic fixture consistency test'} for r in rows]
        self.assertEqual(len(select(rows, CONFIG, report, reviews)['selected']), 4)
        reviews[0]['source_sha256'] = 'obsolete'
        self.assertEqual(len(select(rows, CONFIG, report, reviews)['pending']), 1)

    def test_priority_beats_later_edition_and_conflicts_remain(self):
        # Isolated selector test; evidence validation is exercised independently above.
        a = dict(self.records[0], id='nbs', edition=2025)
        b = dict(self.records[0], id='province', edition=2026, value=200.3)
        report = {'results': [{'id': r['id'], 'machine_checks_passed': True, 'origin': {'capture_matched': True, 'authority': authority}} for r, authority in [(a, {'publisher_id': 'nbs', 'level': 'national'}), (b, {'publisher_id': 'province', 'level': 'province'})]]}
        reviews = [{'record_id': r['id'], 'source_sha256': r['evidence']['sha256'], 'decision': 'approve', 'reviewer': 'test', 'reason': 'selector fixture'} for r in (a, b)]
        self.assertEqual(select([a, b], CONFIG, report, reviews)['selected'][0]['id'], 'nbs')
        c = dict(a, id='conflict', value=999)
        report['results'].append(dict(report['results'][0], id=c['id']))
        reviews.append(dict(reviews[0], record_id=c['id']))
        result = select([a, b, c], CONFIG, report, reviews)
        self.assertEqual((len(result['selected']), len(result['conflicts'])), (0, 1))

    def test_duplicate_review_decisions_rejected(self):
        review = {'record_id': self.records[0]['id']}
        with self.assertRaises(ValueError):
            select(self.records, CONFIG, self.verify(), [review, review])


class BackendTests(unittest.TestCase):
    def test_csv_table(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'table.csv'
            file.write_text('城市,GDP\n廊坊市,100.2\n衡水市,200.3\n', encoding='utf8')
            self.assertEqual(read_source(file, 'csv')['tables'][0]['cells'][2], ['衡水市', '200.3'])

    def test_xlsx_shared_inline_formula(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'fixture.xlsx'
            ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
            with zipfile.ZipFile(file, 'w') as z:
                z.writestr('xl/workbook.xml', '<workbook xmlns="' + ns + '" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="统计表" sheetId="1" r:id="rId1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/sharedStrings.xml', '<sst xmlns="' + ns + '"><si><t>廊坊市</t></si></sst>')
                z.writestr('xl/styles.xml', '<styleSheet xmlns="' + ns + '"><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="10"/></cellXfs></styleSheet>')
                z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="' + ns + '"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>100.2</v></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>衡水市</t></is></c><c r="B2"><f>SUM(B1)</f><v>100.2</v></c></row><row r="3"><c r="B3" s="1"><v>0.072</v></c></row></sheetData></worksheet>')
            table = read_source(file, 'xlsx')['tables'][0]
            self.assertEqual(table['cells'][0], ['廊坊市', '100.2'])
            self.assertEqual(table['cells'][1][0], '衡水市')
            self.assertIn([1, 1], table['formulas'])
            self.assertIn([2, 1], table['display_requires_review'])

    def test_pdf_grid_optional_backend(self):
        try:
            from reportlab.pdfgen import canvas
            import pdfplumber
        except ImportError:
            self.skipTest('Optional PDF dependencies unavailable')
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'fixture.pdf'
            c = canvas.Canvas(str(file))
            for y in (700, 670, 640):
                c.line(50, y, 250, y)
            for x in (50, 150, 250):
                c.line(x, 640, x, 700)
            for x, y, text in ((60, 680, 'City'), (160, 680, 'GDP'), (60, 650, 'Example'), (160, 650, '100.2')):
                c.drawString(x, y, text)
            c.save()
            table = read_source(file, 'pdf')['tables'][0]
            self.assertEqual(table['cells'][1], ['Example', '100.2'])
            self.assertEqual(table['page'], 1)

    def test_configured_source_order(self):
        rules = CONFIG['source_priorities']
        cases = [('government_document', 'nbs', 'national'), ('yearbook', 'province', 'province'), ('communique', 'city', 'city'), ('yearbook', 'city', 'city')]
        ranks = [priority({'source_class': c}, {'publisher_id': p, 'level': l}, rules) for c, p, l in cases]
        self.assertEqual(ranks, [4, 3, 2, 1])

    def test_bounded_catalog(self):
        def response(args):
            return {'sha256': 'hash', 'file': 'source.bin', 'mode': 'network', 'links': [{'url': 'https://www.lf.gov.cn/Item/2.aspx', 'is_statistics_hint': True, 'is_attachment': False}]}
        with tempfile.TemporaryDirectory() as temp, patch('collect_sources.fetch', side_effect=response):
            r = collect('https://www.lf.gov.cn/Item/1.aspx', str(ROOT / 'examples/official_hosts.json'), temp, depth=2, limit=1)
            self.assertEqual(len(r['sources']), 1)
            self.assertTrue(r['limit_reached'])

    def test_exact_hosts_and_redirects(self):
        hosts = {'www.lf.gov.cn': {'publisher': 'test'}}
        for url in ('https://www.lf.gov.cn.evil.invalid/a', 'https://unknown.lf.gov.cn/a', 'file:///tmp/x'):
            with self.assertRaises(ValueError):
                fetch.check_url(url, hosts)
        with self.assertRaises(ValueError):
            fetch.CheckedRedirect(hosts).redirect_request(None, None, 302, '', {}, 'https://example.com/x')


if __name__ == '__main__':
    unittest.main()
