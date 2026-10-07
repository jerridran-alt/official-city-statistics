import json,hashlib,sys,tempfile,unittest,urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from network_health import host_slot,finish,HostDeferred
from collection_efficiency import plan_tables,export_ready
from review_cache import store,lookup
import official_fetch

class EfficiencyTests(unittest.TestCase):
 def test_real_audit_cache_preserves_checks_and_invalidates_on_scope_change(self):
  from test_helpers import CONFIG,MAPPING,REGISTRY
  from stats_core import read_source
  from extract_tables import extract
  from audit_candidates import audit
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'source.html';p.write_bytes((Path(__file__).resolve().parents[1]/'examples/sample_table.html').read_bytes())
   records=extract(read_source(p,'html'),MAPPING,CONFIG,p,Path(d))['records']
   sha=hashlib.sha256(p.read_bytes()).hexdigest();reviews=[{'id':r['id'],'decision':'approve','source_sha256':sha,'reviewer':'fixture reviewer'} for r in records]
   first=audit(records,CONFIG,d,REGISTRY,Path(d)/'cache',reviews);second=audit(records,CONFIG,d,REGISTRY,Path(d)/'cache',reviews)
   self.assertTrue(first['machine_checks_passed']);self.assertEqual(second['audit_cache_hits'],len(records))
   self.assertFalse(second['results'][0]['origin']['capture_matched'])
   changed={**CONFIG,'keep_indicators':[]};third=audit(records,changed,d,REGISTRY,Path(d)/'cache',reviews)
   self.assertEqual(third['audit_cache_hits'],0);self.assertFalse(third['machine_checks_passed'])
 def test_priority_keeps_all_city_extraction(self):
  a={'code':'1','year':2020,'indicator':'energy'};b={**a,'code':'2'}
  result=plan_tables([{'id':'full','expected_keys':[a,b]},{'id':'old','expected_keys':[a],'source_sha256':'ok'},{'id':'unknown'}],[a],['ok'])
  self.assertEqual(result[0]['id'],'full');self.assertEqual(result[0]['expected_new_values'],1);self.assertTrue(result[0]['read_all_cities'])
  self.assertEqual(next(r for r in result if r['id']=='old')['action'],'reuse_reviewed_table');self.assertEqual(next(r for r in result if r['id']=='unknown')['action'],'inspect_unknown_coverage')
 def test_two_failures_block_third_request_and_reset(self):
  with tempfile.TemporaryDirectory() as d:
   for _ in range(2):
    with host_slot(d,'a') as (s,p):finish(s,p,TimeoutError('timeout'),cooldown=30)
   with self.assertRaises(HostDeferred):
    with host_slot(d,'a'):pass
   s=json.loads(p.read_text());s['deferred_until']=0;p.write_text(json.dumps(s))
   with host_slot(d,'a') as (s,p):finish(s,p)
   self.assertEqual(json.loads(p.read_text())['consecutive_failures'],0)
 def test_404_does_not_block_host_but_403_does(self):
  with tempfile.TemporaryDirectory() as d:
   for _ in range(3):
    with host_slot(d,'a') as (s,p):finish(s,p,urllib.error.HTTPError('https://a/x',404,'missing',{},None))
   with host_slot(d,'a') as (s,p):finish(s,p,urllib.error.HTTPError('https://a/x',403,'forbidden',{},None))
   with self.assertRaises(HostDeferred):
    with host_slot(d,'a'):pass
 def test_guard_never_makes_third_network_call(self):
  with tempfile.TemporaryDirectory() as d:
   reg=Path(d)/'registry.json';reg.write_text(json.dumps({'hosts':[{'host':'a','verified':True,'publisher':'Gov','evidence_url':'https://a'}]}))
   args=SimpleNamespace(url='https://a/x',registry=str(reg),output=d,engine='http',html=None,refresh=False,timeout=1)
   with patch.object(official_fetch,'_fetch',side_effect=TimeoutError('timeout')) as call:
    for _ in range(2):
     with self.assertRaises(TimeoutError):official_fetch.fetch(args)
    with self.assertRaises(HostDeferred):official_fetch.fetch(args)
    self.assertEqual(call.call_count,2)
 def test_review_cache_rejects_changed_source_mapping_config_or_review(self):
  with tempfile.TemporaryDirectory() as d:
   source=Path(d)/'source';source.write_bytes(b'original');sha=hashlib.sha256(b'original').hexdigest()
   r={'evidence':{'sha256':sha,'plan_sha256':'p'}};review={'decision':'approve','source_sha256':sha,'plan_sha256':'p'};result={'machine_checks_passed':True}
   self.assertTrue(store(d,r,{}, {},review,'v1',source,result));self.assertTrue(lookup(d,r,{}, {},review,'v1',source)['audit_cache_hit'])
   self.assertIsNone(lookup(d,r,{'scope':'changed'}, {},review,'v1',source));self.assertIsNone(lookup(d,r,{}, {},review,'v2',source));self.assertIsNone(lookup(d,r,{}, {},{**review,'decision':'pending'},'v1',source))
   source.write_bytes(b'changed');self.assertIsNone(lookup(d,r,{}, {},review,'v1',source))
 def test_export_waits_for_province_and_never_claims_gaps_complete(self):
  batch={'province':'a','decision':'collecting','delta_verified':True,'old_keys_preserved':True,'panel_shape_verified':True}
  with self.assertRaises(ValueError):export_ready(batch)
  batch.update(decision='province_complete',pending_tables=['missing'])
  with self.assertRaises(ValueError):export_ready(batch)
  batch['decision']='province_first_pass_closed_with_gaps';self.assertFalse(export_ready(batch)['complete'])

if __name__=='__main__':unittest.main()
