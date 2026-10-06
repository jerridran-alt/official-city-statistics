"""Check capabilities before retrieval; distinguish usable engines from package names."""
import argparse,importlib.util,json,platform,shutil,subprocess
from pathlib import Path
from stats_core import save


def diagnose():
    packages={p:importlib.util.find_spec(p) is not None for p in ('PIL','pypdf','pypdfium2','pdfplumber','playwright','rapidocr','onnxruntime')}
    windows={'available':False}
    if platform.system()=='Windows' and shutil.which('powershell'):
        try:
            run=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('windows_ocr.ps1')),'-Probe'],capture_output=True,text=True,encoding='utf8',timeout=20)
            windows=json.loads(run.stdout.strip().lstrip('\ufeff'))
        except Exception as e:windows={'available':False,'error':str(e)}
    tesseract=shutil.which('tesseract')
    languages=[]
    if tesseract:
        try:
            run=subprocess.run([tesseract,'--list-langs'],capture_output=True,text=True,timeout=10)
            languages=run.stdout.splitlines()[1:]
        except Exception:pass
    rapid=packages['rapidocr'] and packages['onnxruntime']
    browser_binary=False
    if packages['playwright']:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as runtime:browser_binary=Path(runtime.chromium.executable_path).exists()
        except Exception:pass
    image_ready=packages['PIL'] and (windows.get('available',False) or rapid or ('chi_sim' in languages))
    return {'python':platform.python_version(),'platform':platform.system(),'packages':packages,'windows_ocr':windows,'tesseract_languages':languages,'preferred_ocr':'rapidocr' if rapid else 'windows' if windows.get('available') else 'tesseract' if tesseract else None,'capabilities':{'static_html_and_xlsx':True,'text_pdf_tables':packages['pdfplumber'],'pdf_render':packages['pypdfium2'] and packages['PIL'],'chinese_image_ocr':image_ready,'scanned_pdf_ocr':image_ready and packages['pypdfium2'],'browser_render':packages['playwright'] and browser_binary},'note':'Usability checks are not OCR accuracy certification. RapidOCR is preferred for Chinese statistics when installed; Windows/Tesseract are fallbacks. Run a real-source validation after setup.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output');a=p.parse_args()
    result=diagnose()
    if a.output:save(a.output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
