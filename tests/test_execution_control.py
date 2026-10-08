import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from execution_control import PhaseLedger, run_job
from pdf_probe import inspect_pages, probe, sample_pages


class ExecutionTests(unittest.TestCase):
    def test_cover_text_does_not_mask_scanned_body(self):
        visited = []
        def reader(page):
            visited.append(page)
            return 'Statistical yearbook cover text ' * 3 if page == 1 else ''
        result = inspect_pages(138, reader)
        self.assertEqual(result['classification'], 'mixed_sample')
        self.assertEqual(len(visited), 5)
        self.assertIn(69, visited)
        self.assertFalse(result['data_complete'])

    def test_selected_pages_are_original_and_bounded(self):
        self.assertEqual(sample_pages(138, [18]), [18])
        for pages in ([0], [139], list(range(1, 10))):
            with self.assertRaises(ValueError): sample_pages(138, pages)

    def test_arguments_are_passed_as_whole_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = PhaseLedger(Path(directory) / 'ledger.json')
            url = 'https://example.gov.cn/中文/02.a?x=1&y=2'
            result = run_job({'phase': 'parse', 'argv': [sys.executable, '-c', 'import sys; print(sys.argv[1])', url]}, ledger)
            # UTF-8 output independent of Windows inherited console encoding.
            self.assertEqual(result['returncode'], 0)
            self.assertIn('?x=1&y=2', result['stdout'])
            self.assertEqual(len(ledger.data['events']), 1)

    def test_timeout_is_explicit_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = PhaseLedger(Path(directory) / 'ledger.json')
            result = run_job({'phase': 'discovery', 'timeout_seconds': .1, 'argv': [sys.executable, '-c', 'import time; time.sleep(5)']}, ledger)
            self.assertEqual(result['returncode'], 124)
            self.assertFalse(result['data_complete'])
            self.assertEqual(json.loads(ledger.path.read_text())['events'][0]['status'], 'budget_exhausted')

    def test_parallel_intervals_and_unattributed_time(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = PhaseLedger(Path(directory) / 'ledger.json')
            ledger.data = {'started_unix': 100, 'events': [{'phase':'parse','started_unix':102,'ended_unix':108}, {'phase':'ocr','started_unix':105,'ended_unix':110}]}
            with patch('execution_control.time.time', return_value=120): result = ledger.summary(10)
            self.assertEqual(result['unattributed_seconds'], 12)
            self.assertEqual(result['seconds_per_100_new_values'], 200)
            self.assertIsNone(result['tokens'])

    def test_real_pdf_backend_handles_mixed_document(self):
        from reportlab.pdfgen import canvas
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'mixed.pdf'
            c = canvas.Canvas(str(file))
            c.drawString(50, 750, 'Text cover ' * 10); c.showPage()
            c.rect(50, 50, 300, 300); c.showPage(); c.save()
            result = probe(file)
            self.assertEqual(result['classification'], 'mixed_sample')
            self.assertEqual(result['total_pages'], 2)

    def test_directory_budget_preserves_queue_without_fetch(self):
        from province_access import discover
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / 'registry.json'
            registry.write_text('{"hosts": []}')
            with patch('province_access.time.monotonic', side_effect=[0, 2]), patch('province_access.fetch') as fetch:
                result = discover({'province':'Test','catalog_urls':['https://example.gov.cn/']}, str(registry), directory, discovery_seconds=1)
            fetch.assert_not_called()
            self.assertTrue(result['budget_exhausted'])
            self.assertEqual(result['unvisited_catalog_urls'], ['https://example.gov.cn/'])


if __name__ == '__main__': unittest.main()
