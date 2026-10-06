"""Infer common statistical image layouts from OCR coordinates; preserve unresolved evidence."""
import argparse,hashlib,json,re,statistics
from pathlib import Path
from urllib.parse import urlparse
from document_source import read_article,infer_context
from failure_types import SourceFailure,classify
from stats_core import number,norm,save

UNITS=('万吨标准煤','亿千瓦时','万千瓦时','万亿元','亿元','万元','万人','千瓦时','吨标准煤','人','%')
GDP_LABELS={'第二产业增加值':['第二产业'],'第三产业增加值':['第三产业'],'工业增加值':['工业']}


def compatible_unit(indicator,unit):
    if '能源消费' in indicator and '率' not in indicator:return unit in ('万吨标准煤','吨标准煤')
    if '用电量' in indicator:return unit in ('亿千瓦时','万千瓦时','千瓦时')
    if '人口' in indicator and '率' not in indicator:return unit in ('万人','人')
    if '增长率' in indicator or '城镇化率' in indicator:return unit=='%'
    return True


def bands(page):
    rows=[]
    for i,w in sorted(enumerate(page['words']),key=lambda t:t[1]['bbox'][1]+t[1]['bbox'][3]/2):
        x,y,width,height=w['bbox'];cy=y+height/2
        group=next((r for r in rows[-5:] if abs(r['y']-cy)<=max(12,min(40,max(height,r['height'])*.55))),None)
        if group is None:group={'y':cy,'height':height,'indices':[]};rows.append(group)
        group['indices'].append(i)
        high=[page['words'][j]['bbox'][1]+page['words'][j]['bbox'][3]/2 for j in group['indices'] if page['words'][j]['bbox'][3]>=height*.6]
        if high:group['y']=statistics.median(high)
        group['height']=max(group['height'],height)
    for r in rows:r['indices'].sort(key=lambda i:page['words'][i]['bbox'][0])
    return rows


def joined(page,indices):
    return ''.join(page['words'][i]['text'] for i in indices).replace('．','.').replace('，',',').replace('％','%')


def literal_groups(page,indices):
    # Characters/decimal punctuation may be separate OCR words: join only nearby
    # numeric pieces on the same detected row, never invent missing decimal points.
    groups=[]
    for i in indices:
        w=page['words'][i];text=w['text'].replace('．','.').replace('，',',').strip()
        if not re.fullmatch(r'[\d.,+\-％%]+',text):continue
        x,y,width,height=w['bbox']
        if groups:
            last=page['words'][groups[-1][-1]];lx,ly,lw,lh=last['bbox']
            if x-(lx+lw)<max(10,min(height,lh)*.7):groups[-1].append(i);continue
        groups.append([i])
    return [g for g in groups if number(joined(page,g)) is not None]


def alias_labels(indicator,config,caption):
    aliases=[indicator]+config.get('indicator_aliases',{}).get(indicator,[])
    if '地区生产总值' in caption:aliases+=GDP_LABELS.get(indicator,[])
    return aliases


def context_for(source_capture,config,registry,root,parent_capture=None):
    if parent_capture:
        parent=json.loads(Path(parent_capture).read_text(encoding='utf-8-sig'))
        parent_file=Path(parent_capture).parent/parent['file']
        if hashlib.sha256(parent_file.read_bytes()).hexdigest()!=parent['sha256'] or parent_file.stat().st_size!=parent['bytes']:raise ValueError('Parent publication capture hash/size mismatch')
        article=read_article(parent_file,parent['final_url'])
        image=next((v for v in article['images']+article.get('attachments',[]) if v['url']==source_capture['url'] or v['url']==source_capture['final_url']),None)
        if image is None:raise ValueError('Image/PDF attachment is not linked from the original parent article')
        context=infer_context(article,config)
        headings=re.findall(r'(?:表|图)\s*\d+\s*([^\n]+)',image['preceding_text'])
        context['caption']=headings[-1].strip() if headings else ''
        if re.search(r'20\d{2}\s*[—–-]\s*20\d{2}',context['caption']):context['multiyear_figure']=True
        else:
            image_year=re.search(r'(20\d{2})年',context['caption'])
            if image_year:context['year']=int(image_year[1])
        context['parent_context']=image['preceding_text'];return context
    host=urlparse(source_capture['final_url']).hostname
    authority=next((v for v in registry['hosts'] if v['host']==host and v.get('verified') is True),None)
    edition=re.search(r'/(20\d{2})[^/]*/',urlparse(source_capture['final_url']).path)
    city=re.search(r'([^、\s]{2,8}市)统计局',source_capture['publisher'])
    if authority is None or not edition or not city:raise SourceFailure('IMAGE_CONTEXT_UNCERTAIN','图片缺少可确定的城市/书目上下文，需要一次性文档上下文审核，而非猜测')
    unit=next((u for u in config.get('units',[]) if u['name']==city[1]),None)
    return {'city':city[1],'research_id':unit['id'] if unit else None,'edition':int(edition[1]),'source_class':'yearbook','caption':'','title':source_capture['publisher']+' '+edition[1]+'年统计年鉴','context_status':'source_url_inference_requires_review'}


def extract_ocr(file,layout_file,config,root,capture_manifest,registry,parent_capture=None):
    root=Path(root).resolve();file=Path(file).resolve();layout_file=Path(layout_file).resolve();capture_manifest=Path(capture_manifest).resolve()
    capture=json.loads(capture_manifest.read_text(encoding='utf-8-sig'));layout=json.loads(layout_file.read_text(encoding='utf8'))
    digest=hashlib.sha256(file.read_bytes()).hexdigest()
    if layout['source_sha256']!=digest:raise ValueError('OCR artifact and original image/PDF mismatch')
    context=context_for(capture,config,registry,root,parent_capture);records=[];pending=[]
    layout_hash=hashlib.sha256(layout_file.read_bytes()).hexdigest()
    for page in layout['pages']:
        rows=bands(page);year_rows=[]
        for row in rows:
            groups=literal_groups(page,row['indices'])
            year=next((g for g in groups if number(joined(page,g)) in range(1900,2100) and page['words'][g[0]]['bbox'][0]<page['width']*.18),None)
            if year:year_rows.append((row,groups,year))
        if year_rows:
            first_y=min(row['y'] for row,g,y in year_rows);header_top=first_y*.18
            caption=joined(page,[i for i,w in enumerate(page['words']) if w['bbox'][1]<header_top])
            for row,groups,year_group in year_rows:
                year=int(number(joined(page,year_group)))
                if not config['years'][0]<=year<=config['years'][1]:continue
                for group in groups:
                    if group==year_group:continue
                    xs=[page['words'][i]['bbox'][0]+page['words'][i]['bbox'][2]/2 for i in group];center=statistics.mean(xs)
                    other_centers=[statistics.mean(page['words'][i]['bbox'][0]+page['words'][i]['bbox'][2]/2 for i in g) for g in groups if g!=year_group]
                    gap=min((abs(center-v) for v in other_centers if abs(center-v)>5),default=page['width']*.1)
                    header=[i for i,w in enumerate(page['words']) if header_top<=w['bbox'][1]<first_y-row['height'] and abs(w['bbox'][0]+w['bbox'][2]/2-center)<gap*.48]
                    header.sort(key=lambda i:(page['words'][i]['bbox'][1],page['words'][i]['bbox'][0]))
                    text=joined(page,header);matched=[n for n in config['keep_indicators'] if any(norm(a) in norm(text) for a in alias_labels(n,config,caption))]
                    unit=next((u for u in UNITS if u in norm(text)),None)
                    if not matched:continue
                    if unit is None:pending.append({'page':page['page'],'header':text,'reason':'单位未识别，不猜测'});continue
                    for indicator in matched:
                        if not compatible_unit(indicator,unit):pending.append({'page':page['page'],'indicator':indicator,'unit':unit,'reason':'单位/口径不符合该指标；比重不能当原始总量'});continue
                        records.append(make_record(file,layout_file,root,capture_manifest,parent_capture,digest,layout_hash,context,page,indicator,year,unit,group,header,year_group))
        else:
            caption=context.get('parent_context','')
            if 'year' not in context or context.get('multiyear_figure'):
                pending.append({'page':page['page'],'reason':'没有年行，也没有父文献确定数据年'});continue
            year=context['year']
            if not config['years'][0]<=year<=config['years'][1]:pending.append({'page':page['page'],'reason':'图表数据年不在项目观察区间'});continue
            for row in rows:
                if row['y']<page['height']*.1:continue
                label_indices=[i for i in row['indices'] if page['words'][i]['bbox'][0]<page['width']*.42 and re.search(r'[\u3400-\u9fff]',page['words'][i]['text'])]
                label=joined(page,label_indices)
                groups=literal_groups(page,row['indices'])
                groups=[g for g in groups if page['words'][g[0]]['bbox'][0]>=page['width']*.4]
                matched=[n for n in config['keep_indicators'] if any(norm(a)==norm(label) for a in alias_labels(n,config,caption))]
                if not matched or not groups:continue
                first=groups[0];center=statistics.mean(page['words'][i]['bbox'][0]+page['words'][i]['bbox'][2]/2 for i in first)
                headers=[i for i,w in enumerate(page['words']) if w['bbox'][1]<row['y']-row['height'] and abs(w['bbox'][0]+w['bbox'][2]/2-center)<page['width']*.13]
                headers.sort(key=lambda i:(page['words'][i]['bbox'][1],page['words'][i]['bbox'][0]))
                text=joined(page,headers);unit=next((u for u in UNITS if u in norm(text)),None)
                if unit is None:pending.append({'page':page['page'],'label':label,'reason':'数值列单位未识别，需要视觉核对'});continue
                for indicator in matched:
                    if not compatible_unit(indicator,unit):continue
                    records.append(make_record(file,layout_file,root,capture_manifest,parent_capture,digest,layout_hash,context,page,indicator,year,unit,first,label_indices+headers,[]))
    return {'records':records,'pending':pending,'context':context,'data_complete':False,'verification_status':'OCR candidates require source-image visual review'}


def make_record(file,layout_file,root,capture,parent,digest,layout_hash,context,page,indicator,year,unit,value_words,header_words,year_words):
    text=joined(page,value_words);value=number(text)
    identity=json.dumps([digest,layout_hash,page['page'],value_words,indicator,year,context['city']],ensure_ascii=False)
    source_row=hashlib.sha256((digest+str(page['page'])+str(value_words)).encode()).hexdigest()[:24]
    return {'id':hashlib.sha256(identity.encode()).hexdigest()[:24],'research_id':context.get('research_id'),'source_row_id':source_row,'identity_status':'matched' if context.get('research_id') else 'unmapped','city':context['city'],'year':year,'indicator':indicator,'unit':unit,'value':value,'source_class':context['source_class'],'edition':context['edition'],'geographic_scope':'全市','is_derived':False,'evidence':{'kind':'ocr_layout','file':file.relative_to(root).as_posix(),'sha256':digest,'ocr_artifact':layout_file.relative_to(root).as_posix(),'ocr_sha256':layout_hash,'page':page['page'],'value_words':value_words,'header_words':header_words,'year_words':year_words,'value_text':text,'capture_manifest':Path(capture).resolve().relative_to(root).as_posix(),'parent_capture':Path(parent).resolve().relative_to(root).as_posix() if parent else None,'context':context},'review_requirements':['原图数字、单位、年份和行列','OCR一致性不是字形真实性','书目上下文/城市范围']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','layout','config','evidence-root','capture-manifest','registry','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--parent-capture');a=p.parse_args()
    try:
        config=json.loads(Path(a.config).read_text(encoding='utf-8-sig'));registry=json.loads(Path(a.registry).read_text(encoding='utf-8-sig'))
        result=extract_ocr(a.input,a.layout,config,a.evidence_root,a.capture_manifest,registry,a.parent_capture)
        status='extracted_candidates' if result['records'] else 'unparsed'
        if result['records']:save(a.output,result['records'])
        save(a.output+'.report.json',{k:v for k,v in result.items() if k!='records'}|{'status':status,'records':len(result['records'])})
        print(json.dumps({'status':status,'records':len(result['records']),'pending':len(result['pending'])},ensure_ascii=False));return 0 if result['records'] else 1
    except Exception as exc:
        report={'status':'unparsed','records':0,'data_complete':False,'failure':classify(exc)};save(a.output+'.report.json',report);print(json.dumps(report,ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
