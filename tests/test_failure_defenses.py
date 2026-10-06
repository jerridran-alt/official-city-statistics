import copy,hashlib,json,subprocess,sys,tempfile,unittest,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from stats_core import table_health,save,read_source
from extract_tables import extract
from audit_candidates import audit
from document_extract import extract_article
from failure_types import SourceFailure,classify
from ocr_extract import compatible_unit


class DefenseTests(unittest.TestCase):
    def test_incompatible_high_priority_scope_is_excluded(self):
        from select_panel import select
        records=[{'id':'national','research_id':'110000','city':'北京市','year':2025,'indicator':'GDP','geographic_scope':'全国','unit':'亿元','value':999,'source_class':'yearbook','edition':2026,'evidence':{'sha256':'hash'}},{'id':'local','research_id':'110000','city':'北京市','year':2025,'indicator':'GDP','geographic_scope':'全市','unit':'亿元','value':100,'source_class':'communique','edition':2026,'evidence':{'sha256':'hash'}}]
        config={'units':[{'id':'110000'}],'allowed_geographic_scopes':{'default':['全市']},'source_priorities':[{'match':{'publisher_id':'nbs'}},{'match':{}}]}
        report={'results':[{'id':r['id'],'machine_checks_passed':True,'origin':{'capture_matched':True,'authority':{'publisher_id':'nbs' if r['id']=='national' else 'local'}}} for r in records]}
        reviews=[{'record_id':r['id'],'source_sha256':'hash','decision':'approve','reviewer':'fixture','reason':'selector test'} for r in records]
        result=select(records,config,report,reviews);self.assertEqual(result['selected'][0]['id'],'local');self.assertEqual(len(result['excluded_from_panel']),1)
    def test_collapsed_numeric_cells_quarantined(self):
        spec={'data_start_row':1,'columns':[{'header_cells':[[0,1]]}]}
        table={'cells':[['City','GDP (USD)'],['Langfang 100.2 20.5',''],['Beijing','100.2']]}
        self.assertIn('MULTIPLE_VALUES_IN_CELL',{r['code'] for r in table_health(table,spec)})
    def test_broken_header_and_zero_rows(self):
        spec={'data_start_row':1,'columns':[{'header_cells':[[0,1]]}]}
        self.assertIn('BROKEN_HEADER',{r['code'] for r in table_health({'cells':[['City','GDP (USD'],['Beijing','100']]},spec)})
        self.assertIn('NO_DATA_ROWS',{r['code'] for r in table_health({'cells':[['City','GDP']]},spec)})
    def test_ragged_columns(self):
        self.assertIn('INCONSISTENT_COLUMNS',{r['code'] for r in table_health({'cells':[['City','GDP'],['Beijing','100','unexpected']]},{'data_start_row':1,'columns':[]})})
    def test_zero_audit_is_not_success(self):
        report=audit([],{'years':[2024,2025]},'.',{'hosts':[]});self.assertFalse(report['machine_checks_passed']);self.assertEqual(report['status'],'empty_input')
    def test_network_and_parser_failures_are_distinct(self):
        self.assertTrue(classify(urllib.error.URLError('timeout'))['retryable'])
        self.assertFalse(classify(urllib.error.HTTPError('url',404,'missing',None,None))['retryable'])
        self.assertFalse(classify(SourceFailure('NO_STRUCTURED_TABLES','no tables',0))['retryable'])
        self.assertEqual(classify(SourceFailure('NO_STRUCTURED_TABLES','no tables',0))['category'],'parse')
    def test_ratio_not_accepted_as_energy_total(self):
        self.assertFalse(compatible_unit('能源消费总量','%'));self.assertTrue(compatible_unit('能源消费总量','万吨标准煤'))
    def test_zero_record_cli_fails_and_blocks_downstream(self):
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp);html=d/'input.html';html.write_text('<h1>2025年统计年鉴</h1><p>地域范围：全市</p><table><tr><th>城市</th><th>2024 GDP (USD)</th></tr><tr><td>省合计</td><td>100</td></tr></table>',encoding='utf8')
            config={'years':[2024,2024],'units':[],'keep_indicators':['GDP']};mapping={'source_class':'yearbook','edition':2025,'class_quote':'统计年鉴','edition_quote':'2025年统计年鉴','tables':[{'table_index':0,'city_column':0,'data_start_row':1,'scope':'全市','scope_quote':'地域范围：全市','columns':[{'column':1,'indicator':'GDP','year':2024,'unit':'USD','header_cells':[[0,1]]}]}]}
            save(d/'config.json',config);save(d/'mapping.json',mapping);save(d/'registry.json',{'hosts':[]})
            run=subprocess.run([sys.executable,str(ROOT/'scripts/extract_tables.py'),'--input',str(html),'--format','html','--config',str(d/'config.json'),'--mapping',str(d/'mapping.json'),'--output',str(d/'candidates.json'),'--cache-dir',str(d/'cache'),'--evidence-root',str(d)],capture_output=True,text=True,encoding='utf8')
            self.assertNotEqual(run.returncode,0);report=json.loads(run.stdout);self.assertEqual(report['status'],'empty_or_error');self.assertEqual(report['records'],0)
            # Simulate a stale output from an earlier successful run: report gate blocks it.
            save(d/'candidates.json',[])
            blocked=subprocess.run([sys.executable,str(ROOT/'scripts/audit_candidates.py'),'--records',str(d/'candidates.json'),'--config',str(d/'config.json'),'--evidence-root',str(d),'--registry',str(d/'registry.json'),'--output',str(d/'audit.json')],capture_output=True,text=True,encoding='utf8')
            self.assertNotEqual(blocked.returncode,0);self.assertEqual(json.loads(blocked.stdout)['status'],'upstream_failed')


class ArticleRegression(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.file=self.root/'article.html'
        self.file.write_text('<meta name="ArticleTitle" content="北京市2025年国民经济和社会发展统计公报"><meta name="PubDate" content="2026-03-25"><div class="TRS_UEDITOR"><p>全年实现地区生产总值100.2亿元，比上年增长5.4%。</p><p>人均地区生产总值23.9万元。</p><p>京津冀协同发展。区域实现地区生产总值11.99万亿元，比上年增长5.4%。</p><p>2024年实现地区生产总值90.1亿元。</p><p>年末全市常住人口[4]2180.0万人。</p><p>全年城镇新增就业33.0万人。</p></div>',encoding='utf8')
        self.config={'years':[2025,2025],'units':[{'id':'110000','name':'北京市'}],'keep_indicators':['地区生产总值','地区生产总值增长率','年末常住人口','全社会从业人员']}
        self.capture=self.root/'capture.json';save(self.capture,{'url':'https://www.example.gov.cn/article','final_url':'https://www.example.gov.cn/article','file':self.file.name,'sha256':hashlib.sha256(self.file.read_bytes()).hexdigest(),'bytes':self.file.stat().st_size,'mode':'offline_html','publisher':'test fixture'})
    def test_actual_city_year_and_stock_eligibility(self):
        result=extract_article(self.file,self.config,self.root,self.capture)
        self.assertEqual({r['indicator'] for r in result['records']},{'地区生产总值','地区生产总值增长率','年末常住人口'})
        self.assertEqual(next(r['value'] for r in result['records'] if r['indicator']=='地区生产总值'),100.2)
        self.assertGreaterEqual(len(result['excluded_mentions']),3)
    def test_prose_replay_rejects_tampered_value(self):
        rows=extract_article(self.file,self.config,self.root,self.capture)['records'];self.assertTrue(audit(rows,self.config,self.root,{'hosts':[]})['machine_checks_passed']);rows[0]['value']=999;self.assertFalse(audit(rows,self.config,self.root,{'hosts':[]})['machine_checks_passed'])
    def test_wrong_year_not_accepted(self):
        config=copy.deepcopy(self.config);config['years']=[2024,2024]
        with self.assertRaises(SourceFailure):extract_article(self.file,config,self.root,self.capture)


if __name__=='__main__':unittest.main()
