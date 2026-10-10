import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collection_efficiency import plan_tables

class YieldTests(unittest.TestCase):
 def test_measured_cost_prioritizes_new_values_per_work_not_raw_rows(self):
  keys=[{'code':str(i),'year':2024,'indicator':'GDP'} for i in range(20)]
  tables=[{'id':'slow','yearbook_level':'province','expected_keys':keys,'estimated_seconds':100},{'id':'fast','yearbook_level':'province','expected_keys':keys[:10],'estimated_seconds':10}]
  ranked=plan_tables(tables,[])
  self.assertEqual(ranked[0]['id'],'fast');self.assertTrue(all(t['read_all_cities'] for t in ranked))
 def test_known_revision_cannot_disappear_into_duplicate_cache(self):
  k={'code':'1','year':2024,'indicator':'GDP'}
  for field in ['newer_eligible_edition','scope_changed','same_source_correction_due']:
   r=plan_tables([{'id':'recheck','expected_keys':[k],'source_sha256':'s',field:True,'yearbook_level':'province'}],[k],['s'])[0]
   self.assertNotEqual(r['action'],'reuse_reviewed_table');self.assertTrue(r['version_review_due'])
if __name__=='__main__':unittest.main()
