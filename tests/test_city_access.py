import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from city_access import lookup,plan_city

class CityAccessTests(unittest.TestCase):
 def test_supplied_urls_and_empty_entries_are_preserved(self):
  cat=json.loads((Path(__file__).resolve().parents[1]/'assets/city_yearbook_urls.json').read_text(encoding='utf8'))
  self.assertEqual(len(cat['entries']),369);self.assertEqual(sum(bool(e['yearbook_url']) for e in cat['entries']),246);self.assertEqual(sum(not e['yearbook_url'] for e in cat['entries']),123)
  self.assertEqual(lookup('澄迈县')['retrieval_level'],'city')
  self.assertEqual(lookup('梅州市')['yearbook_url'],'https://www.meizhou.gov.cn/zwgk/zfjg/stjj/mindex.html');self.assertIsNone(lookup('吕梁市')['yearbook_url'])
 def test_municipalities_reuse_provincial_layer(self):
  for name in ['北京市','天津市','上海市','重庆市']:
   self.assertEqual(plan_city(name,[])['action'],'reuse_province_layer');self.assertEqual(lookup(name)['retrieval_level'],'province')
 def test_city_url_is_only_used_after_documented_province_gap(self):
  gap={'code':'441400','year':2024,'indicator':'energy'}
  self.assertEqual(plan_city('梅州市',[gap])['action'],'defer_until_provincial_gap_checked')
  check={**gap,'level':'province','status':'missing','reason':'省原表空项','source_refs':['source-table.json']}
  self.assertEqual(plan_city('梅州市',[gap],[check])['action'],'use_supplied_city_url')
 def test_unknown_unit_never_gets_guessed_url(self):
  self.assertEqual(lookup('未知城市')['action'],'not_in_url_catalog');self.assertIsNone(lookup('未知城市')['yearbook_url'])

if __name__=='__main__':unittest.main()
