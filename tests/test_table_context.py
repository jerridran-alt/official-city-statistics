import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from table_context import publication_context

class PublicationContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.target='https://stats.example.gov.cn/2025/table.htm'
        self.registry={'hosts':[{'host':'stats.example.gov.cn','publisher':'示例统计局','evidence_url':'https://stats.example.gov.cn','verified':True}]}
    def tearDown(self):self.tmp.cleanup()
    def capture(self,name,url,text):
        data=text.encode();(self.root/(name+'.html')).write_bytes(data)
        m={'final_url':url,'file':name+'.html','sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'mode':'network','publisher':'示例统计局'}
        (self.root/(name+'.json')).write_text(json.dumps(m),encoding='utf8')
        return name+'.json'
    def test_literal_onclick_and_link_chain(self):
        a=self.capture('book','https://stats.example.gov.cn/2025/index.htm','<title>统计年鉴2025</title><td onclick="location.href=\'chapter.htm\'">能源</td>')
        b=self.capture('chapter','https://stats.example.gov.cn/2025/chapter.htm','<a href="table.htm">用电</a>')
        self.assertIn('统计年鉴2025',publication_context([a,b],self.root,self.target,self.registry))
    def test_unlinked_publication_not_accepted(self):
        a=self.capture('book','https://stats.example.gov.cn/2025/index.htm','<title>统计年鉴2025</title>')
        with self.assertRaisesRegex(ValueError,'link missing'):publication_context([a],self.root,self.target,self.registry)
    def test_tampered_source_rejected(self):
        a=self.capture('book','https://stats.example.gov.cn/2025/index.htm','<a href="table.htm">统计年鉴2025</a>')
        (self.root/'book.html').write_text('forged',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):publication_context([a],self.root,self.target,self.registry)
    def test_unregistered_or_cross_host_rejected(self):
        a=self.capture('book','https://stats.example.gov.cn/2025/index.htm','<a href="table.htm">统计年鉴2025</a>')
        with self.assertRaisesRegex(ValueError,'not registered'):publication_context([a],self.root,self.target,{'hosts':[]})
        with self.assertRaisesRegex(ValueError,'same official host'):publication_context([a],self.root,'https://another.gov.cn/table.htm',self.registry)

if __name__=='__main__':unittest.main()
