import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collection_efficiency import plan_tables
from select_panel import priority

class YearbookHierarchyTests(unittest.TestCase):
 def test_unknown_level_cannot_be_assumed_province_and_bulletin_is_not_yearbook(self):
  a={'code':'1','year':2024,'indicator':'energy'}
  r=plan_tables([{'source_class':'yearbook','expected_keys':[a]}],[])[0]
  self.assertEqual(r['action'],'inspect_publication_level_metadata_only')
  r=plan_tables([{'source_class':'communique','authority_level':'city','expected_keys':[a]}],[])[0]
  self.assertFalse(r['action'].startswith('defer_lower_yearbook'))
 def setUp(self):
  self.a={'code':'1','year':2024,'indicator':'energy','geographic_scope':'full_city'}
  self.b={**self.a,'code':'2'}
 def check(self,level,status='missing'):
  return {**self.a,'level':level,'status':status,'reason':'原表缺项或真实访问失败','source_refs':['capture/original-table-or-failure-report.json']}
 def test_province_precedes_high_yield_city_and_lower_is_deferred(self):
  tables=[{'id':'city','yearbook_level':'city','expected_keys':[self.a,self.b]},{'id':'province','yearbook_level':'province','expected_keys':[self.a]}]
  r=plan_tables(tables,[]);self.assertEqual(r[0]['id'],'province');self.assertTrue(r[1]['action'].startswith('defer_'))
 def test_only_documented_unfilled_keys_unlock_city_table(self):
  t={'yearbook_level':'city','expected_keys':[self.a,self.b]};r=plan_tables([t],[],fallback_checks=[self.check('province')])[0]
  self.assertEqual(r['unlocked_gap_count'],1);self.assertEqual(r['deferred_gap_count'],1);self.assertTrue(r['read_all_cities'])
  r=plan_tables([t],[self.a],fallback_checks=[self.check('province')])[0];self.assertEqual(r['unlocked_gap_count'],0)
 def test_county_is_not_a_collection_stage(self):
  t={'yearbook_level':'county','expected_keys':[self.a]}
  self.assertEqual(plan_tables([t],[],fallback_checks=[self.check('province')])[0].get('unlocked_gap_count',0),0)
  self.assertEqual(plan_tables([t],[],fallback_checks=[self.check('province'),self.check('city')])[0]['action'],'exclude_outside_province_city_collection_levels')
 def test_unavailable_upper_level_is_recorded_and_pending_is_not_missing(self):
  t={'yearbook_level':'city','expected_keys':[self.a]}
  self.assertEqual(plan_tables([t],[],fallback_checks=[self.check('province','unavailable')])[0]['unlocked_gap_count'],1)
  self.assertEqual(plan_tables([t],[],fallback_checks=[self.check('province','pending_review')])[0].get('unlocked_gap_count',0),0)
  bare=self.check('province');bare['source_refs']=[];self.assertEqual(plan_tables([t],[],fallback_checks=[bare])[0].get('unlocked_gap_count',0),0)
 def test_source_priority_is_yearbook_then_communique_then_other(self):
  config=json.loads((Path(__file__).resolve().parents[1]/'examples/project.json').read_text(encoding='utf8'))
  ranks=[priority({'source_class':c},{'publisher_id':'local','level':'province'},config['source_priorities']) for c in ['yearbook','communique','government_document']]
  self.assertEqual(ranks,[3,2,1]);self.assertEqual(priority({'source_class':'government_document'},{'publisher_id':'nbs','level':'national'},config['source_priorities']),1)

if __name__=='__main__':unittest.main()
