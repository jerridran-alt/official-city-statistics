"""Local OCR for PDF/image with rendering, tiled word coordinates and cache provenance."""
import argparse,hashlib,importlib.util,json,platform,shutil,subprocess,tempfile,time
from pathlib import Path
from stats_core import save


def choose_engine(requested='auto'):
    if requested!='auto':return requested
    if importlib.util.find_spec('rapidocr') and importlib.util.find_spec('onnxruntime'):return 'rapidocr'
    if platform.system()=='Windows' and shutil.which('powershell'):
        from doctor import diagnose
        if diagnose()['windows_ocr'].get('available'):return 'windows'
    if importlib.util.find_spec('rapidocr') and importlib.util.find_spec('onnxruntime'):return 'rapidocr'
    if shutil.which('tesseract'):return 'tesseract'
    raise RuntimeError('No Chinese OCR backend available. Run doctor.py, then bootstrap.py --profile ocr, or install a supported OCR language/backend.')


def render_pages(source,scale,max_pages=5):
    try:from PIL import Image
    except ImportError as exc:raise RuntimeError('Image/PDF OCR requires Pillow; run bootstrap.py --profile basic') from exc
    if source.suffix.lower()=='.pdf' or source.read_bytes()[:5]==b'%PDF':
        try:import pypdfium2 as pdfium
        except ImportError as exc:raise RuntimeError('Scanned PDF rendering requires pypdfium2; run bootstrap.py --profile basic') from exc
        doc=pdfium.PdfDocument(source)
        for i in range(min(len(doc),max_pages)):
            bitmap=doc[i].render(scale=scale);image=bitmap.to_pil().convert('RGB')
            yield i+1,image
        doc.close()
    else:
        with Image.open(source) as im:
            yield 1,im.convert('RGB').resize((round(im.width*scale),round(im.height*scale)))


def run_ocr(source,cache_dir,engine='auto',scale=3.0,language='zh-Hans-CN',tile_size=3000,min_confidence=.85,max_pages=5):
    source=Path(source).resolve();digest=hashlib.sha256(source.read_bytes()).hexdigest();engine=choose_engine(engine)
    if engine=='windows':
        from doctor import diagnose
        tile_size=min(tile_size,diagnose()['windows_ocr'].get('max_dimension',tile_size))
    profile={'engine':engine,'scale':scale,'language':language,'tile_size':tile_size,'version':'1.1','min_confidence':min_confidence,'max_pages':max_pages}
    if engine=='windows':profile['backend_script_sha256']=hashlib.sha256(Path(__file__).with_name('windows_ocr.ps1').read_bytes()).hexdigest()
    key=hashlib.sha256((digest+json.dumps(profile,sort_keys=True)).encode()).hexdigest()
    cache=(Path(cache_dir)/key).resolve();cache.mkdir(parents=True,exist_ok=True);result_file=cache/'layout.json';checksum=cache/'layout.sha256'
    if result_file.exists() and checksum.exists() and hashlib.sha256(result_file.read_bytes()).hexdigest()==checksum.read_text().strip():
        data=json.loads(result_file.read_text(encoding='utf8'))
        if data.get('source_sha256')!=digest or data.get('profile')!=profile:raise ValueError('OCR cache identity/profile mismatch')
        if not any(p.get('words') for p in data.get('pages',[])):
            from failure_types import SourceFailure
            raise SourceFailure('OCR_EMPTY','缓存OCR也为0词，来源未解析，非数据齐全')
        return data,result_file,True
    started=time.monotonic();jobs=[];pages=[];tiles=[]
    for page_no,image in render_pages(source,scale,max_pages):
        path=cache/f'page-{page_no}.png';image.save(path)
        pages.append({'page':page_no,'image_file':path.name,'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'width':image.width,'height':image.height,'words':[]})
        step=max(1,tile_size-120)
        for top in range(0,image.height,step):
            for left in range(0,image.width,step):
                tile=cache/f'p{page_no}-x{left}-y{top}.png';image.crop((left,top,min(image.width,left+tile_size),min(image.height,top+tile_size))).save(tile)
                output=tile.with_suffix('.ocr.json')
                if output.exists():
                    previous=json.loads(output.read_text(encoding='utf-8-sig'))
                    if previous.get('error'):output.unlink()
                job={'path':str(tile),'output':str(output)};jobs.append(job);tiles.append({'page':page_no,'left':left,'top':top,'output':output})
    if engine=='windows':
        save(cache/'jobs.json',jobs)
        run=subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('windows_ocr.ps1')),'-JobsFile',str(cache/'jobs.json'),'-LanguageTag',language],capture_output=True,text=True,encoding='utf8',timeout=max(60,20*len(jobs)))
        if run.returncode:raise RuntimeError('Windows OCR failed: '+run.stdout+run.stderr)
    elif engine=='rapidocr':
        from rapidocr import RapidOCR
        model=RapidOCR()
        for job in jobs:
            result=model(job['path']);words=[]
            for box,text,score in zip(result.boxes if result.boxes is not None else [],result.txts if result.txts is not None else [],result.scores if result.scores is not None else []):
                xs=[float(v[0]) for v in box];ys=[float(v[1]) for v in box]
                words.append({'text':text,'x':min(xs),'y':min(ys),'width':max(xs)-min(xs),'height':max(ys)-min(ys),'confidence':float(score)})
            save(job['output'],{'lines':[{'words':words}]})
    elif engine=='tesseract':
        import csv,io
        for job in jobs:
            run=subprocess.run(['tesseract',job['path'],'stdout','-l','chi_sim+eng','tsv'],capture_output=True,text=True,encoding='utf8',timeout=60)
            if run.returncode:raise RuntimeError(run.stderr)
            words=[{'text':r['text'],'x':float(r['left']),'y':float(r['top']),'width':float(r['width']),'height':float(r['height']),'confidence':float(r['conf'])/100} for r in csv.DictReader(io.StringIO(run.stdout),delimiter='\t') if r.get('text','').strip()]
            save(job['output'],{'lines':[{'words':words}]})
    else:raise ValueError('Unknown OCR engine: '+engine)
    for tile in tiles:
        doc=json.loads(tile['output'].read_text(encoding='utf-8-sig'))
        if doc.get('error'):raise RuntimeError(doc['error'])
        page=pages[tile['page']-1]
        for line in doc['lines']:
            for w in line['words']:
                item={'text':w['text'],'bbox':[w['x']+tile['left'],w['y']+tile['top'],w['width'],w['height']],'confidence':w.get('confidence')}
                x,y,width,height=item['bbox']
                if not any(v['text']==item['text'] and abs(v['bbox'][0]-x)<5 and abs(v['bbox'][1]-y)<5 for v in page['words']):page['words'].append(item)
    for page in pages:
        page['words'].sort(key=lambda w:(w['bbox'][1],w['bbox'][0]))
        page['text']=' '.join(w['text'] for w in page['words'])
    if not any(p['words'] for p in pages):
        from failure_types import SourceFailure
        raise SourceFailure('OCR_EMPTY','OCR 识别到 0 个词，来源未解析，非数据齐全')
    review=[{'page':p['page'],'word_index':i,'text':w['text'],'bbox':w['bbox'],'confidence':w['confidence'],'reason':'score_unavailable' if w['confidence'] is None else 'low_score'} for p in pages for i,w in enumerate(p['words']) if w['confidence'] is None or w['confidence']<min_confidence]
    data={'source_sha256':digest,'source_name':source.name,'profile':profile,'pages':pages,'seconds':round(time.monotonic()-started,3),'ocr_status':'needs_visual_review','note':'Coordinates refer to the rendered page pixels. OCR consistency is not proof of glyph accuracy.'}
    data['low_confidence_review']=review
    if source.suffix.lower()=='.pdf' or source.read_bytes()[:5]==b'%PDF':
        import pypdfium2 as pdfium
        check=pdfium.PdfDocument(source);data['total_pdf_pages']=len(check);check.close();data['pages_queued']=max(0,data['total_pdf_pages']-len(pages))
    else:data['pages_queued']=0
    import html
    rows=''.join('<tr style="background:#ffe2e2"><td>'+str(r['page'])+'</td><td>'+html.escape(r['text'])+'</td><td>'+html.escape(str(r['confidence']))+'</td><td>'+html.escape(str(r['bbox']))+'</td></tr>' for r in review)
    (cache/'ocr_review.html').write_text('<meta charset="utf-8"><h1>低分或无评分 OCR 词：待视觉核查</h1><p>高评分也不能代替字形核验。以下红色仅是审核优先级。</p><table><tr><th>页</th><th>识别词</th><th>分数</th><th>位置</th></tr>'+rows+'</table>',encoding='utf8')
    save(result_file,data);checksum.write_text(hashlib.sha256(result_file.read_bytes()).hexdigest(),encoding='ascii')
    return data,result_file,False


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--cache-dir',required=True);p.add_argument('--language',default='zh-Hans-CN')
    p.add_argument('--engine',choices=('auto','windows','rapidocr','tesseract'),default='auto');p.add_argument('--scale',type=float,default=3)
    p.add_argument('--max-pages',type=int,default=5);p.add_argument('--min-confidence',type=float,default=.85)
    a=p.parse_args()
    try:
        if not 1<=a.max_pages<=100 or not 0<=a.min_confidence<=1:raise ValueError('max-pages must be 1..100; min-confidence must be 0..1')
        data,artifact,reused=run_ocr(a.input,a.cache_dir,a.engine,a.scale,language=a.language,min_confidence=a.min_confidence,max_pages=a.max_pages);save(a.output,data)
        print(json.dumps({'status':'ocr_candidates','pages':len(data['pages']),'words':sum(len(p['words']) for p in data['pages']),'engine':data['profile']['engine'],'cache_reused':reused,'layout':str(artifact),'seconds':data['seconds'],'review_words':len(data.get('low_confidence_review',[]))}))
        return 0
    except Exception as exc:
        from failure_types import classify
        report={'status':'unparsed','failure':classify(exc),'words':0,'data_complete':False};save(a.output+'.report.json',report);print(json.dumps(report,ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
