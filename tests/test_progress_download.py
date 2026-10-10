import json,os,sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from official_fetch import _fetch
from progress_download import DownloadDeferred
from execution_control import PhaseLedger

class ProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ranges=[];cls.mode='slow'
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def do_GET(self):
                data=b'abcdefghij';offset=int(self.headers.get('Range','bytes=0-').split('=')[1].split('-')[0]);ProgressTests.ranges.append((self.headers.get('Range'),self.headers.get('If-Range')))
                mode=ProgressTests.mode
                if mode=='ignore':offset=0
                self.send_response(206 if offset else 200);self.send_header('Content-Type','application/octet-stream');self.send_header('ETag','"stable"');self.send_header('Content-Length',str(len(data)-offset))
                if offset:self.send_header('Content-Range',f'bytes {offset}-9/10')
                self.end_headers()
                try:
                    for v in data[offset:]:
                        self.wfile.write(bytes([v]));self.wfile.flush()
                        time.sleep(.25 if mode=='stall' else .025)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=cls.server.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def args(self,d,**extra):
        url=f'http://127.0.0.1:{self.server.server_port}/fixture';reg=Path(d)/'registry.json';reg.write_text(json.dumps({'hosts':[{'host':'127.0.0.1','publisher':'Synthetic fixture only','verified':True,'evidence_url':url}]}))
        return SimpleNamespace(**{'url':url,'registry':str(reg),'output':str(Path(d)/'capture'),'engine':'http','refresh':False,'html':None,'encoding':None,'timeout':.1,'retries':0,'max_bytes':100,'network_route':'direct',**extra})
    def test_active_download_exceeds_idle_timeout_and_completes(self):
        self.mode='slow';ProgressTests.mode='slow'
        with tempfile.TemporaryDirectory() as d:
            a=self.args(d);t=time.monotonic();r=_fetch(a)
            self.assertGreater(time.monotonic()-t,a.timeout);self.assertEqual(r['bytes'],10)
            self.assertEqual((Path(a.output)/r['file']).read_bytes(),b'abcdefghij');self.assertFalse(list(Path(a.output).glob('*.part')))
    def test_work_quota_preserves_and_resumes_validated_range(self):
        ProgressTests.mode='slow';ProgressTests.ranges=[]
        with tempfile.TemporaryDirectory() as d:
            a=self.args(d,max_seconds=.065)
            with self.assertRaises(DownloadDeferred):_fetch(a)
            self.assertTrue(list(Path(a.output).glob('*.part')))
            self.assertFalse([p for p in Path(a.output).glob('*.json') if len(p.stem)==24])
            a.max_seconds=None;r=_fetch(a)
            self.assertGreater(r['resumed_bytes'],0);self.assertEqual((Path(a.output)/r['file']).read_bytes(),b'abcdefghij')
            self.assertEqual(ProgressTests.ranges[-1][1],'"stable"')
    def test_no_progress_timeout_keeps_partial_without_success_manifest(self):
        ProgressTests.mode='stall'
        with tempfile.TemporaryDirectory() as d:
            a=self.args(d)
            with self.assertRaises(TimeoutError):_fetch(a)
            self.assertTrue(list(Path(a.output).glob('*.part')));self.assertFalse(list(Path(a.output).glob('*.bin')))
    def test_server_ignoring_range_restarts_instead_of_duplicating(self):
        ProgressTests.mode='slow'
        with tempfile.TemporaryDirectory() as d:
            a=self.args(d,max_seconds=.065)
            with self.assertRaises(DownloadDeferred):_fetch(a)
            ProgressTests.mode='ignore';a.max_seconds=None;r=_fetch(a)
            self.assertEqual(r['resumed_bytes'],0);self.assertEqual((Path(a.output)/r['file']).read_bytes(),b'abcdefghij')
    def test_tampered_partial_is_rejected(self):
        ProgressTests.mode='slow'
        with tempfile.TemporaryDirectory() as d:
            a=self.args(d,max_seconds=.065)
            with self.assertRaises(DownloadDeferred):_fetch(a)
            next(Path(a.output).glob('*.part')).write_bytes(b'tamper');a.max_seconds=None
            with self.assertRaisesRegex(ValueError,'Partial download changed'):_fetch(a)
    def test_ledger_origin_and_manual_phases_are_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ledger.json'
            with patch('execution_control.time.time',return_value=100):PhaseLedger(p)
            with patch('execution_control.time.time',return_value=110):ledger=PhaseLedger(p);ledger.start_phase('visual_review','table1')
            with patch('execution_control.time.time',return_value=120):ledger.finish_phase('table1');summary=ledger.summary(2)
            self.assertEqual(ledger.data['started_unix'],100);self.assertEqual(summary['phase_seconds']['visual_review'],10)
            self.assertEqual(summary['unattributed_seconds'],10)
    def test_direct_route_is_scoped_and_proxy_requires_explicit_env(self):
        ProgressTests.mode='slow'
        with tempfile.TemporaryDirectory() as d:
            original=dict(os.environ);r=_fetch(self.args(d));self.assertEqual(r['network_route'],'direct');self.assertEqual(dict(os.environ),original)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):_fetch(self.args(d,network_route='proxy',proxy_env='ABSENT_TEST_PROXY'))

if __name__=='__main__':unittest.main()
