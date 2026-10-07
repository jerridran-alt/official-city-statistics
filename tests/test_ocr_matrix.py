import hashlib,json,sys,tempfile,unittest,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ocr_matrix import propose,extract_matrix
from audit_candidates import audit
from select_panel import select

class MatrixTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=self.root/'original.bin';self.source.write_bytes(b'synthetic OCR interpretation fixture, not an official image')
        self.sha=hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.layout=self.root/'layout.json';self.plan=self.root/'plan.json';self.capture=self.root/'capture.json'
        self.registry={'hosts':[{'host':'stats.example.gov.cn','publisher':'Fixture Statistics','verified':True,'evidence_url':'https://stats.example.gov.cn'}]}
        self.config={'years':[2020,2024],'units':[{'id':'1','name':'甲城市','aliases':[]}],'keep_indicators':['全社会用电量'],'source_priorities':[{'name':'fixture','match':{}}]}
        self.dump(self.capture,{'final_url':'https://stats.example.gov.cn/tjnj/2025/test.jpg','file':'original.bin','sha256':self.sha,'bytes':self.source.stat().st_size,'publisher':'Fixture Statistics','mode':'network','note':'synthetic test fixture only'})
    def tearDown(self):self.tmp.cleanup()
    def dump(self,path,value):path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf8')
    def page(self,n,cities=('甲城市','乙城市'),values=(('1.2','2.3'),('3.4','4.5'))):
        words=[]
        def add(t,x,y,width=70):words.append({'text':t,'bbox':[x,y,width,20],'confidence':.99})
        add('8-8 全社会用电量',10,20,200);add('单位：亿千瓦时',10,55,180)
        add('2023',330,100,40);add('2024',530,100,40)
        for i,(city,vals) in enumerate(zip(cities,values)):
            add(city,10,160+i*60,160)
            for x,v in zip([330,530],vals):add(v,x,160+i*60,55)
        return {'page':n,'width':800,'height':500,'words':words}
    def prepare(self,pages=None,queued=0):
        data={'source_sha256':self.sha,'pages':pages or [self.page(1)],'pages_queued':queued}
        self.dump(self.layout,data);plan=propose(data,self.config);plan['publication']={'edition':2025,'source_class':'yearbook'}
        for spec in plan['pages']:spec['table_key']='8-8'
        self.dump(self.plan,plan);return data,plan
    def extract(self):return extract_matrix(self.source,self.layout,self.plan,self.config,self.root,self.capture,self.registry)
    def test_all_city_rows_preserved_before_research_filter(self):
        self.prepare();result=self.extract()
        self.assertEqual(len(result['records']),4);self.assertEqual(result['source_city_labels'],2)
        self.assertEqual(sum(r['research_id'] is None for r in result['records']),2)
        self.assertFalse(result['pending'])
    def test_footnote_city_label_not_collapsed(self):
        self.prepare([self.page(1,('甲城市','甲城市①'))]);r=self.extract()
        self.assertEqual({x['city'] for x in r['records']},{'甲城市','甲城市①'})
        self.assertEqual(sum(x['research_id'] is None for x in r['records']),2)
    def test_vertical_repeated_headers_two_original_pages(self):
        self.prepare([self.page(4,('甲城市',)),self.page(9,('乙城市',))]);r=self.extract()
        self.assertEqual(len(r['records']),4);self.assertFalse(r['pending'])
        self.assertEqual({x['evidence']['page'] for x in r['records']},{4,9})
    def test_missing_page_map_and_unread_pages_fail(self):
        data,plan=self.prepare(queued=1)
        with self.assertRaisesRegex(ValueError,'Unread'):self.extract()
        plan['explicit_table_page_subset']=True;self.dump(self.plan,plan);self.assertEqual(len(self.extract()['records']),4)
        plan['page_scope']=[1,2];self.dump(self.plan,plan)
        with self.assertRaisesRegex(ValueError,'coverage'):self.extract()
    def test_different_printed_tables_cannot_join(self):
        data,plan=self.prepare([self.page(1),self.page(2,('丙城市',))]);plan['pages'][1]['table_key']='9-9';self.dump(self.plan,plan)
        with self.assertRaisesRegex(ValueError,'identities disagree'):self.extract()
    def test_inherited_headers_require_same_identity_and_geometry(self):
        data,plan=self.prepare([self.page(1,('甲城市',)),self.page(2,('乙城市',))]);s=plan['pages'][1]
        for col in s['columns']:col['header_refs']=[[1,i] for page,i in col['header_refs']]
        s['continues_page']=1;self.dump(self.plan,plan);self.assertEqual(len(self.extract()['records']),4)
        s['columns'][0]['x'][0]+=.03;self.dump(self.plan,plan)
        with self.assertRaisesRegex(ValueError,'geometry drift'):self.extract()
    def test_duplicate_city_year_keys_remain_pending(self):
        self.prepare([self.page(1),self.page(2)]);r=self.extract();self.assertTrue(r['pending'])
        self.assertFalse(audit(r['records'],self.config,self.root,self.registry)['machine_checks_passed'])
    def test_scope_and_unit_not_guessed(self):
        data,plan=self.prepare();plan['pages'][0]['scope']='全市';self.dump(self.plan,plan)
        with self.assertRaisesRegex(ValueError,'scope'):self.extract()
        plan['pages'][0]['scope']='原表城市行';plan['pages'][0]['columns'][0]['unit']='万吨标准煤';self.dump(self.plan,plan)
        with self.assertRaisesRegex(ValueError,'header'):self.extract()
    def test_wide_numeric_box_is_quarantined(self):
        data,plan=self.prepare();data['pages'][0]['words'][5]['bbox'][2]=170;self.dump(self.layout,data)
        self.assertTrue(self.extract()['pending'])
    def test_tampered_value_or_plan_hash_cannot_pass_audit(self):
        self.prepare();r=self.extract()['records'];report=audit(r,self.config,self.root,self.registry);self.assertEqual(report['passed'],4)
        r[0]['value']=99;self.assertEqual(audit(r,self.config,self.root,self.registry)['failed'],1)
        r=self.extract()['records'];r[0]['evidence']['plan_sha256']='bad';self.assertEqual(audit(r,self.config,self.root,self.registry)['failed'],1)
    def test_source_approval_without_plan_hash_is_pending(self):
        self.prepare();r=self.extract()['records'];report=audit(r,self.config,self.root,self.registry)
        reviews=[{'record_id':x['id'],'source_sha256':self.sha,'reviewer':'test fixture','reason':'fixture rule','decision':'approve'} for x in r]
        self.assertEqual(len(select(r,self.config,report,reviews)['pending']),2)
        for rev,x in zip(reviews,r):rev['plan_sha256']=x['evidence']['plan_sha256']
        self.assertEqual(len(select(r,self.config,report,reviews)['selected']),2)
    def test_edited_plan_invalidates_existing_review(self):
        self.prepare();r=self.extract()['records'];old_hash=r[0]['evidence']['plan_sha256']
        plan=json.loads(self.plan.read_text(encoding='utf8'));plan['review_note']='layout reviewed again';self.dump(self.plan,plan)
        new=self.extract()['records'];self.assertNotEqual(old_hash,new[0]['evidence']['plan_sha256'])
        self.assertEqual(audit(r,self.config,self.root,self.registry)['failed'],4)
    def test_adjacent_column_unit_cannot_be_borrowed(self):
        data,plan=self.prepare();data['pages'][0]['words'][1]['text']='亿千瓦时';data['pages'][0]['words'][1]['bbox'][0]=700;self.dump(self.layout,data)
        with self.assertRaisesRegex(ValueError,'another column'):self.extract()
    def test_qualified_subrow_keeps_full_scope_label(self):
        self.prepare([self.page(1,('甲城市','#甲城市(不含新区)'))]);r=self.extract()
        self.assertEqual({x['city'] for x in r['records']},{'甲城市','#甲城市(不含新区)'})
        self.assertFalse(r['pending'])
    def test_horizontal_continuation_uses_own_indicator_unit(self):
        first=self.page(1,('甲城市',));second=self.page(2,('甲城市',))
        second['words'][0]['text']='8-8 工业用电量'
        self.config['keep_indicators'].append('工业用电量');data,plan=self.prepare([first,second]);s=plan['pages'][1];s['continues_page']=1
        for col in s['columns']:
            col['header_refs']=[[1,i] if i in (2,3) else [pn,i] for pn,i in col['header_refs']]
        self.dump(self.plan,plan);r=self.extract();self.assertEqual(len(r['records']),4);self.assertFalse(r['pending'])
    def test_partial_cli_nonzero_and_downstream_block(self):
        data,plan=self.prepare();data['pages'][0]['words'][5]['bbox'][2]=170;self.dump(self.layout,data)
        config=self.root/'config.json';registry=self.root/'registry.json';out=self.root/'records.json'
        self.dump(config,self.config);self.dump(registry,self.registry)
        script=Path(__file__).resolve().parents[1]/'scripts/ocr_matrix.py'
        args=[sys.executable,str(script),'--input',str(self.source),'--layout',str(self.layout),'--plan',str(self.plan),'--config',str(config),'--evidence-root',str(self.root),'--capture-manifest',str(self.capture),'--registry',str(registry),'--output',str(out)]
        run=subprocess.run(args,capture_output=True,text=True,encoding='utf8');self.assertEqual(run.returncode,1)
        self.assertEqual(json.loads(Path(str(out)+'.report.json').read_text(encoding='utf8'))['status'],'partial_pending')
        check=subprocess.run([sys.executable,str(script.with_name('audit_candidates.py')),'--records',str(out),'--config',str(config),'--evidence-root',str(self.root),'--registry',str(registry),'--output',str(self.root/'audit.json')],capture_output=True,text=True,encoding='utf8')
        self.assertEqual(check.returncode,1);self.assertEqual(json.loads((self.root/'audit.json').read_text(encoding='utf8'))['status'],'upstream_failed')

if __name__=='__main__':unittest.main()
