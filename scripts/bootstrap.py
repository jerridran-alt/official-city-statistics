"""Set up an isolated runtime; never install into the user's global Python."""
import argparse,os,subprocess,sys,venv
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--venv',default='.venv');p.add_argument('--profile',choices=('basic','ocr','browser','test'),default='basic')
    a=p.parse_args();target=Path(a.venv).resolve()
    if not (target/'pyvenv.cfg').exists():venv.EnvBuilder(with_pip=True).create(target)
    python=target/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    packages=['Pillow>=10','pypdfium2>=4.30','pypdf>=5','pdfplumber>=0.11']
    if a.profile=='ocr':packages+=['rapidocr>=2.0.3','onnxruntime>=1.17']
    if a.profile=='browser':packages+=['playwright>=1.49']
    if a.profile=='test':packages+=['reportlab>=4']
    subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','--timeout','20','--retries','1']+packages,check=True)
    if a.profile=='browser':subprocess.run([str(python),'-m','playwright','install','chromium'],check=True)
    print('Isolated Python:',python)
    subprocess.run([str(python),str(Path(__file__).with_name('doctor.py'))],check=True)


if __name__=='__main__':main()
