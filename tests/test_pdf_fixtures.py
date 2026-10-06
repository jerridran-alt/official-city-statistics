"""Required PDF regression suite: missing PDF test dependencies are errors, not green skips."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
from reportlab.pdfgen import canvas
import pdfplumber

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from stats_core import read_source,save
from extract_tables import extract
from failure_types import SourceFailure

CONFIG={'years':[2024,2024],'units':[{'id':'110000','name':'Beijing'},{'id':'131000','name':'Langfang'}],'keep_indicators':['GDP','Power']}
MAPPING={'source_class':'yearbook','edition':2025,'class_quote':'Statistical Yearbook 2025','edition_quote':'2025','tables':[{'table_index':0,'city_column':0,'data_start_row':1,'scope':'city','scope_quote':'Scope: city','columns':[{'column':1,'indicator':'GDP','year':2024,'unit':'USD','header_cells':[[0,1]]},{'column':2,'indicator':'Power','year':2024,'unit':'kWh','header_cells':[[0,2]]}]}]}


def fixture(file,kind):
    c=canvas.Canvas(str(file));c.drawString(50,790,'Statistical Yearbook 2025');c.drawString(50,770,'Scope: city')
    if kind=='borderless':
        for x,y,t in [(50,710,'City'),(220,710,'2024 GDP (USD)'),(380,710,'2024 Power (kWh)'),(50,680,'Beijing'),(220,680,'100.2'),(380,680,'20.5')]:c.drawString(x,y,t)
    elif kind=='normal':
        for y in (740,710,680,650):c.line(50,y,530,y)
        for x in (50,210,370,530):c.line(x,650,x,740)
        for x,y,t in [(60,720,'City'),(220,720,'2024 GDP (USD)'),(380,720,'2024 Power (kWh)'),(60,690,'Beijing'),(220,690,'100.2'),(380,690,'20.5'),(60,660,'Langfang'),(220,660,'200.3'),(380,660,'30.6')]:c.drawString(x,y,t)
    else:
        for y in (740,710,680,650,620):c.line(50,y,530,y)
        for x in (50,210,530):c.line(x,620,x,740)
        c.line(370,620,370,710)
        # The top header is merged; the next complete visual text crosses a ruling,
        # a common fragmentation failure in PDF cell reconstruction.
        for x,y,t in [(60,720,'City'),(280,720,'2024'),(330,690,'GDP (USD)'),(450,690,'Power (kWh)'),(60,660,'Beijing'),(220,660,'100.2'),(380,660,'20.5'),(60,630,'Langfang'),(220,630,'200.3'),(380,630,'30.6')]:c.drawString(x,y,t)
    c.save()


class PDFRegression(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def test_borderless_is_zero_tables_and_explicit_failure(self):
        file=self.root/'borderless.pdf';fixture(file,'borderless')
        with self.assertRaises(SourceFailure) as caught:read_source(file,'pdf')
        self.assertEqual((caught.exception.code,caught.exception.detected_tables),('NO_STRUCTURED_TABLES',0))
        save(self.root/'config.json',CONFIG);save(self.root/'mapping.json',MAPPING)
        run=subprocess.run([sys.executable,str(ROOT/'scripts/extract_tables.py'),'--input',str(file),'--format','pdf','--config',str(self.root/'config.json'),'--mapping',str(self.root/'mapping.json'),'--output',str(self.root/'data.json'),'--cache-dir',str(self.root/'cache'),'--evidence-root',str(self.root)],capture_output=True,text=True,encoding='utf8')
        self.assertNotEqual(run.returncode,0);report=json.loads(run.stdout)
        self.assertEqual(report['detected_tables'],0);self.assertFalse(report['data_complete']);self.assertIn('非数据齐全',report['failure']['reason'])
    def test_merged_fragmented_pdf_quarantined(self):
        import copy
        file=self.root/'merged.pdf';fixture(file,'merged');parsed=read_source(file,'pdf')
        mapping=copy.deepcopy(MAPPING);spec=mapping['tables'][0];spec['data_start_row']=2
        for col in spec['columns']:col['header_cells']=[[0,col['column']],[1,col['column']]]
        result=extract(parsed,mapping,CONFIG,file,self.root)
        self.assertEqual(len(result['records']),0)
        self.assertTrue(any(e.get('code')=='SUSPICIOUS_TABLE_STRUCTURE' for e in result['errors']))
    def test_normal_multicolumn_pdf_city_rows(self):
        file=self.root/'normal.pdf';fixture(file,'normal');parsed=read_source(file,'pdf');result=extract(parsed,MAPPING,CONFIG,file,self.root)
        self.assertFalse(result['errors']);self.assertEqual([r['value'] for r in result['records']],[100.2,20.5,200.3,30.6]);self.assertEqual({r['city'] for r in result['records']},{'Beijing','Langfang'})


if __name__=='__main__':unittest.main()
