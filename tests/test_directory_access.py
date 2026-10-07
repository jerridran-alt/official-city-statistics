import json,tempfile,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import official_fetch
from province_access import discover
from network_health import HostDeferred

class DirectoryAccessTests(unittest.TestCase):
 def test_year_search_and_self_navigation_are_not_yearbook_entries(self):
  with tempfile.TemporaryDirectory() as d:
   reg=Path(d)/'registry';reg.write_text(json.dumps({'hosts':[{'host':'gov.test','verified':True}]}))
   record={'final_url':'https://gov.test/catalog','sha256':'original','document_title':'统计数据','links':[{'url':'https://gov.test/search.htm?s=2014','text':'2014'},{'url':'https://gov.test/catalog','text':'2021年统计年鉴'}]}
   with patch('province_access.fetch',return_value=record):r=discover({'province':'测试','portal_url':'https://gov.test/catalog'},reg,Path(d)/'capture')
   self.assertEqual(r['yearbook_entries'],[]);self.assertEqual(len(r['pending_year_links']),1)
 def test_primary_user_entry_precedes_retained_fallback(self):
  with tempfile.TemporaryDirectory() as d:
   reg=Path(d)/'registry';reg.write_text(json.dumps({'hosts':[{'host':'gov.test','verified':True}]}))
   record={'final_url':'http://gov.test/old/catalog','sha256':'original','links':[{'url':'http://gov.test/book','text':'统计年鉴2025'}]}
   with patch('province_access.fetch',side_effect=[TimeoutError('primary timed out'),record]) as f:
    r=discover({'province':'测试','portal_url':'http://gov.test','catalog_urls':['http://gov.test/new/catalog'],'fallback_catalog_urls':['http://gov.test/old/catalog'],'discovery_page_limit':2},reg,Path(d)/'capture')
   self.assertEqual([c.args[0].url for c in f.call_args_list],['http://gov.test/new/catalog','http://gov.test/old/catalog']);self.assertEqual(r['yearbook_entries'][0]['edition'],2025)
 def test_direct_book_and_year_only_labels_use_original_metadata(self):
  with tempfile.TemporaryDirectory() as d:
   reg=Path(d)/'registry';reg.write_text(json.dumps({'hosts':[{'host':'gov.test','verified':True}]}))
   record={'final_url':'https://gov.test/book','sha256':'original','document_title':'测试统计年鉴2025','links':[{'url':'https://gov.test/2024','text':'2024'}]}
   with patch('province_access.fetch',return_value=record):
    r=discover({'province':'测试','portal_url':'https://gov.test','catalog_urls':['https://gov.test/book'],'entry_kind':'direct_yearbook'},reg,Path(d)/'capture')
   self.assertEqual([a['edition'] for a in r['yearbook_entries']],[2025,2024])
 def test_cdata_catalog_preserves_literal_protocol_and_special_path(self):
  data='<meta charset="utf-8"><script><record><![CDATA[<a href="http://gov.test/tjnj/nj2015/new/indexch_new.htm" title="统计年鉴2015">统计年鉴2015</a>]]></record></script>'.encode()
  links=official_fetch.inspect_html(data,'http://gov.test/col/index.html')
  self.assertEqual(len(links),1);self.assertEqual(links[0]['url'],'http://gov.test/tjnj/nj2015/new/indexch_new.htm');self.assertEqual(links[0]['discovery'],'embedded_cdata')
 def test_charset_and_frame_do_not_change_protocol(self):
  data='<meta charset="gb2312"><frame name="contents" src="left.htm"><a href="html\\0616.htm">统计年鉴2024</a>'.encode('gb18030')
  enc=official_fetch.html_encoding(data);self.assertEqual(enc,'gb18030');links=official_fetch.inspect_html(data,'http://gov.test/book/indexch.htm',enc)
  self.assertTrue(links[0]['is_catalog_frame']);self.assertEqual(links[0]['url'],'http://gov.test/book/left.htm');self.assertEqual(links[1]['url'],'http://gov.test/book/html/0616.htm')
 def test_https_failure_does_not_suspend_http(self):
  with tempfile.TemporaryDirectory() as d:
   registry=Path(d)/'registry';registry.write_text(json.dumps({'hosts':[{'host':'gov.test','publisher':'Gov','verified':True,'evidence_url':'http://gov.test'}]}))
   def args(url):return SimpleNamespace(url=url,registry=str(registry),output=d,engine='http',html=None,refresh=False,timeout=1)
   with patch.object(official_fetch,'_fetch',side_effect=TimeoutError('TLS handshake timeout')):
    for _ in range(2):
     with self.assertRaises(TimeoutError):official_fetch.fetch(args('https://gov.test/x'))
    with self.assertRaises(HostDeferred):official_fetch.fetch(args('https://gov.test/y'))
   with patch.object(official_fetch,'_fetch',return_value={'status':'ok'}) as network:
    self.assertEqual(official_fetch.fetch(args('http://gov.test/catalog')),{'status':'ok'});self.assertEqual(network.call_count,1)
 def test_profiles_cover_31_and_do_not_contain_synthetic_year_urls(self):
  profiles=json.loads((Path(__file__).resolve().parents[1]/'examples/china_province_access.json').read_text(encoding='utf8'))['provinces']
  self.assertEqual(len(profiles),31);self.assertEqual(len({p['code_prefix'] for p in profiles}),31);self.assertFalse({'香港','澳门','台湾'}&{p['province'] for p in profiles})
  self.assertTrue(all('{year}' not in str(p) for p in profiles))
 def test_discovery_uses_returned_final_url_and_actual_yearbook_links(self):
  with tempfile.TemporaryDirectory() as d:
   reg=Path(d)/'registry';reg.write_text(json.dumps({'hosts':[{'host':'gov.test','verified':True}]}))
   record={'final_url':'http://gov.test/current/catalog','sha256':'original','encoding':'utf8','links':[{'url':'http://gov.test/special/2015/start.htm','text':'统计年鉴2015'}]}
   with patch('province_access.fetch',return_value=record):
    report=discover({'province':'测试','portal_url':'http://gov.test','catalog_urls':['http://gov.test/catalog']},reg,Path(d)/'capture')
   self.assertEqual(report['yearbook_entries'][0]['url'],'http://gov.test/special/2015/start.htm');self.assertEqual(report['yearbook_entries'][0]['discovered_from'],'http://gov.test/current/catalog')

if __name__=='__main__':unittest.main()
