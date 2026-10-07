import sys,tempfile,unittest
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ocr_layout import render_pages

class PDFPageSelectionTests(unittest.TestCase):
    def test_binary_cache_pdf_keeps_original_selected_page_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'original.bin';c=Canvas(str(source))
            for n in range(1,4):c.drawString(20,40,str(n));c.showPage()
            c.save();pages=list(render_pages(source,1,max_pages=2,page_numbers=[1,3]))
            self.assertEqual([n for n,image in pages],[1,3])
    def test_out_of_document_page_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'original.bin';c=Canvas(str(source));c.drawString(20,40,'1');c.showPage();c.save()
            with self.assertRaisesRegex(ValueError,'outside original'):list(render_pages(source,1,max_pages=1,page_numbers=[2]))

if __name__=='__main__':unittest.main()
