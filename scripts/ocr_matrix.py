"""Reviewable multi-city OCR matrices with explicit page/column evidence, never ordinal joins."""
import argparse,hashlib,json,re,statistics
from pathlib import Path
from urllib.parse import urlparse
from ocr_extract import bands,joined,literal_groups,compatible_unit,UNITS
from stats_core import number,norm,save
from failure_types import SourceFailure,classify

VERSION='1.0'
CITY=re.compile(r'^([\u3400-\u9fff]{1,20}(?:自治州|地区|市|县|盟|旗|区)[①②③④⑤⑥⑦⑧⑨⑩*]*(?:[（(][\u3400-\u9fff0-9，、]+[）)])?)')

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def relative(root,path):
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()

def refs_text(pages,refs):
    parts=[]
    for ref in refs:
        if not isinstance(ref,list) or len(ref)!=2 or any(type(i)!=int or i<0 for i in ref):raise ValueError('Invalid [page, word_index] anchor')
        page,index=ref
        parts.append(pages[page]['words'][index]['text'])
    return ''.join(parts).replace('．','.').replace('％','%')

def propose(layout,config):
    """Propose only repeated city-row/year-column layouts; human inspects saved plan."""
    specs=[];pending=[]
    for page in layout['pages']:
        rows=bands(page);candidates=[]
        for row in rows:
            years=[i for i in row['indices'] if re.fullmatch(r'(?:19|20)\d{2}',page['words'][i]['text'].strip())]
            if len(years)>=2 and row['y']<page['height']*.6:candidates.append((row,years))
        if len(candidates)!=1:
            pending.append({'page':page['page'],'reason':'年份表头不唯一或未识别；需要显式页映射'});continue
        row,years=candidates[0];top=[i for i,w in enumerate(page['words']) if w['bbox'][1]+w['bbox'][3]/2<row['y']]
        text=joined(page,top);indicators=[n for n in config['keep_indicators'] if norm(n) in norm(text)]
        units=[u for u in UNITS if u in norm(text)]
        # Longer units take precedence only when the shorter token is contained.
        units=[u for u in units if not any(u!=v and u in v for v in units)]
        if len(indicators)!=1 or len(units)!=1:
            pending.append({'page':page['page'],'reason':'指标/单位不唯一；不继承上一页猜测'});continue
        years.sort(key=lambda i:page['words'][i]['bbox'][0])
        centers=[(page['words'][i]['bbox'][0]+page['words'][i]['bbox'][2]/2)/page['width'] for i in years]
        gap=min(b-a for a,b in zip(centers,centers[1:]));left=centers[0]-gap/2
        bounds=[left]+[(a+b)/2 for a,b in zip(centers,centers[1:])]+[min(1,centers[-1]+gap/2)]
        columns=[{'indicator':indicators[0],'year':int(page['words'][i]['text']),'unit':units[0],'x':[bounds[j],bounds[j+1]],'header_refs':[[page['page'],i]]+[[page['page'],k] for k in top if norm(indicators[0]) in norm(page['words'][k]['text']) or units[0] in norm(page['words'][k]['text'])]} for j,i in enumerate(years)]
        specs.append({'page':page['page'],'city_x':[0,left],'body_y':[min(1,(row['y']+row['height'])/page['height']),1],'columns':columns,'scope':'原表城市行','scope_refs':[], 'table_refs':[[page['page'],k] for k in top if norm(indicators[0]) in norm(page['words'][k]['text'])]})
    return {'version':VERSION,'source_sha256':layout['source_sha256'],'page_scope':[p['page'] for p in layout['pages']],'pages':specs,'proposal_pending':pending,'review_status':'proposal_requires_source_image_review','note':'同名脚注行保留原标签，不去掉①；未定义续表/城市列缺失时不按行序拼接。'}

def extract_matrix(source,layout_file,plan_file,config,root,capture_manifest,registry):
    root=Path(root).resolve();source=Path(source).resolve();layout_file=Path(layout_file).resolve();plan_file=Path(plan_file).resolve()
    for file in (source,layout_file,plan_file,Path(capture_manifest).resolve()):file.relative_to(root)
    layout=json.loads(layout_file.read_text(encoding='utf-8-sig'));plan=json.loads(plan_file.read_text(encoding='utf-8-sig'))
    cap_path=Path(capture_manifest).resolve();cap=json.loads(cap_path.read_text(encoding='utf-8-sig'))
    sha=digest(source);layout_sha=digest(layout_file);plan_sha=digest(plan_file)
    captured_file=(cap_path.parent/cap['file']).resolve();captured_file.relative_to(root)
    if layout.get('source_sha256')!=sha or plan.get('source_sha256')!=sha or cap['sha256']!=sha or cap['bytes']!=source.stat().st_size or digest(captured_file)!=sha:raise ValueError('Matrix source/layout/plan/capture identity mismatch')
    authority=next((a for a in registry['hosts'] if a.get('host')==urlparse(cap['final_url']).hostname and a.get('verified') is True and a.get('publisher')==cap['publisher'] and a.get('evidence_url')),None)
    if authority is None:raise ValueError('Matrix publisher not registered')
    publication=plan.get('publication',{});edition=publication.get('edition');source_class=publication.get('source_class')
    if type(edition)!=int or source_class not in ('yearbook','communique','government_document'):raise ValueError('Explicit publication edition/class required')
    # Edition can be inferred only as a reviewable candidate, not certified metadata.
    context_chain=publication.get('context_chain',[])
    if publication.get('document_quote'):
        quote=publication['document_quote'];page=publication.get('document_page')
        with source.open('rb') as f:prefix=f.read(5)
        if prefix!=b'%PDF-' or type(page)!=int or page<1:raise ValueError('Original PDF publication quote requires a valid original page')
        from pypdf import PdfReader
        reader=PdfReader(source)
        if page>len(reader.pages) or norm(quote) not in norm(reader.pages[page-1].extract_text() or '') or str(edition) not in quote or (source_class=='yearbook' and '年鉴' not in quote):raise ValueError('Publication class/edition not supported by original PDF page quote')
        context_status='original_pdf_publication_quote_requires_semantic_review'
    elif context_chain:
        from table_context import publication_context
        text=publication_context(context_chain,root,cap['final_url'],registry)
        for quote in [publication.get('title_quote'),publication.get('edition_quote')]:
            if not quote or norm(quote) not in norm(text):raise ValueError('Publication quote unsupported by linked original captures')
        if str(edition) not in publication['edition_quote']:raise ValueError('Edition unsupported by publication quote')
        context_status='linked_publication_requires_semantic_review'
    else:
        if str(edition) not in urlparse(cap['final_url']).path:raise ValueError('Edition not supported by source URL; supply linked publication context')
        if source_class=='yearbook' and not re.search(r'(?:tjnj|/nj|yearbook|nianjian)',cap['final_url'],re.I):raise ValueError('Yearbook context uncertain; supply linked publication context')
        context_status='source_url_book_year_inference_requires_review'
    pages={p['page']:p for p in layout['pages']};specs=plan['pages'];scope=plan.get('page_scope',[])
    if len(set(scope))!=len(scope) or sorted(scope)!=sorted(pages) or sorted(s['page'] for s in specs)!=sorted(scope):raise ValueError('Page coverage mismatch: explicitly map every OCR page; do not silently skip unparsed pages')
    if len(specs)>1 and (not specs[0].get('table_key') or any(s.get('table_key')!=specs[0]['table_key'] for s in specs)):raise ValueError('Cross-page table identities disagree')
    if layout.get('pages_queued',0) and not plan.get('explicit_table_page_subset',False):raise ValueError('Unread pages remain; declare a reviewed table page subset or finish OCR')
    records=[];pending=list(plan.get('proposal_pending',[]));skipped=[];labels=set();row_total=0
    aliases={}
    for u in config.get('units',[]):
        for label in [u['name']]+u.get('aliases',[]):
            if norm(label) in aliases and aliases[norm(label)]['id']!=u['id']:raise ValueError('Ambiguous city alias')
            aliases[norm(label)]=u
    schema_by_page={}
    for spec in specs:
        page=pages[spec['page']];columns=spec['columns'];geometry=[];schema=[]
        for col in columns:
            indicator=col['indicator'];year=col['year'];unit=col['unit'];x=col['x']
            if len(x)!=2 or not 0<=x[0]<x[1]<=1:raise ValueError('Invalid normalized column interval')
            head=norm(refs_text(pages,col['header_refs']))
            allowed=[indicator]+config.get('indicator_aliases',{}).get(indicator,[])
            if not any(norm(a) in head for a in allowed) or str(year) not in head or norm(unit) not in head:raise ValueError('Matrix indicator/year/unit not supported by original header word anchors')
            if not compatible_unit(indicator,unit):raise ValueError('Indicator/unit mismatch')
            if year>edition:raise ValueError('Observation year later than publication edition')
            unit_anchors=[]
            for pn,wi in col['header_refs']:
                word=pages[pn]['words'][wi];text=norm(word['text']);center=(word['bbox'][0]+word['bbox'][2]/2)/pages[pn]['width']
                if norm(unit) in text and ('单位' in text or x[0]<=center<x[1]):unit_anchors.append((pn,wi))
                if text==str(year) and not x[0]<=center<x[1]:raise ValueError('Year header belongs to another numeric column')
            if not unit_anchors:raise ValueError('Unit header belongs to another column; do not borrow adjacent units')
            geometry.append(x);schema.append((indicator,year,unit))
        if any(a[1]>b[0] for a,b in zip(geometry,geometry[1:])):raise ValueError('Overlapping/unordered value columns')
        schema_by_page[spec['page']]=(schema,geometry)
        inherited=any(ref[0]!=spec['page'] for col in columns for ref in col['header_refs'])
        if inherited:
            previous=spec.get('continues_page');key=spec.get('table_key')
            if previous not in schema_by_page or previous==spec['page'] or not key or norm(key) not in norm(refs_text(pages,spec.get('table_refs',[]))):raise ValueError('Header inheritance needs an already mapped page and same printed table identity')
            if any(ref[0] not in (previous,spec['page']) for col in columns for ref in col['header_refs']):raise ValueError('Continuation refers to a different unmapped page')
            own_headers=[norm(refs_text(pages,[ref for ref in col['header_refs'] if ref[0]==spec['page']])) for col in columns]
            own_schema=all(any(norm(a) in head for a in [col['indicator']]+config.get('indicator_aliases',{}).get(col['indicator'],[])) and norm(col['unit']) in head for col,head in zip(columns,own_headers))
            if own_schema:
                # Horizontal continuation may contain other indicators/columns.
                # Only the printed year is inherited; its source must be anchored.
                for col in columns:
                    if str(col['year']) not in norm(refs_text(pages,[r for r in col['header_refs'] if r[0]==previous])):raise ValueError('Continuation year not printed on linked preceding page')
            else:
                ps,pg=schema_by_page[previous]
                if schema!=ps or any(abs(a-b)>.02 for x,y in zip(geometry,pg) for a,b in zip(x,y)):raise ValueError('Continuation header/geometry drift; cannot inherit')
        else:
            if len(specs)>1 and not spec.get('table_key'):raise ValueError('Multi-page matrix needs explicit printed table identity on every page')
            if spec.get('table_key') and norm(spec['table_key']) not in norm(refs_text(pages,spec.get('table_refs',[]))):raise ValueError('Printed table identity is absent')
        scope_name=spec.get('scope','原表城市行');scope_text=refs_text(pages,spec.get('scope_refs',[]))
        if any(ref[0]!=spec['page'] for ref in spec.get('table_refs',[])):raise ValueError('Each page must retain its own printed table identity')
        if scope_name!='原表城市行' and norm(scope_name) not in norm(scope_text):raise ValueError('Declared statistical scope lacks original word evidence')
        city_x=spec['city_x'];body_y=spec['body_y']
        if not 0<=city_x[0]<city_x[1]<=geometry[0][0] or not 0<=body_y[0]<body_y[1]<=1:raise ValueError('City/body ranges overlap data or exceed page')
        page_rows=0
        for row in bands(page):
            if not body_y[0]<=row['y']/page['height']<=body_y[1]:continue
            city_words=[i for i in row['indices'] if city_x[0]<=(page['words'][i]['bbox'][0]+page['words'][i]['bbox'][2]/2)/page['width']<city_x[1] and re.search(r'[\u3400-\u9fff]',page['words'][i]['text'])]
            raw_label=joined(page,city_words);label=norm(raw_label)
            ignored=spec.get('skip_city_labels',[])+['全市','全省','全国','全区','合计','总计','省合计']
            if any(label.startswith(norm(x)) for x in ignored):
                skipped.append({'page':page['page'],'label':raw_label,'reason':'explicit non-admin aggregate label'});continue
            hierarchy=label.startswith(('#','＃'));match=CITY.match(label.lstrip('#＃'))
            if not match:
                if city_words:skipped.append({'page':page['page'],'label':raw_label,'reason':'not an explicit city/admin label; aggregate/footer retained in original'})
                continue
            city=match[1];tail=label.lstrip('#＃')[len(city):]
            if tail and not re.fullmatch(r'[A-Za-z①②③④⑤⑥⑦⑧⑨⑩*]+',tail):
                pending.append({'page':page['page'],'label':raw_label,'reason':'城市标签混杂/断行，禁止猜测身份'});continue
            # English can share an OCR box with the literal Chinese label. The
            # exact original mixed label remains in evidence; annotation stays.
            if hierarchy:city='#'+city
            unit_identity=aliases.get(norm(city));labels.add(city);row_total+=1;page_rows+=1
            groups=literal_groups(page,row['indices']);row_cells=0
            for col in columns:
                if col['indicator'] not in config['keep_indicators'] or not config['years'][0]<=col['year']<=config['years'][1]:continue
                candidates=[]
                for g in groups:
                    center=statistics.mean(page['words'][i]['bbox'][0]+page['words'][i]['bbox'][2]/2 for i in g)/page['width']
                    if col['x'][0]<=center<col['x'][1]:candidates.append(g)
                if len(candidates)!=1:
                    tokens=[page['words'][i]['text'] for i in row['indices'] if col['x'][0]<=(page['words'][i]['bbox'][0]+page['words'][i]['bbox'][2]/2)/page['width']<col['x'][1]]
                    if len(candidates)==0 and tokens and all(norm(t) in ('—','–','...','..','未公布','不详') for t in tokens):skipped.append({'page':page['page'],'city':city,'year':col['year'],'reason':'explicit source missing marker'})
                    else:pending.append({'page':page['page'],'city':city,'indicator':col['indicator'],'year':col['year'],'reason':'0或多个候选值，单元格未解析；不填零、不按邻列补数'})
                    continue
                group=candidates[0];text=joined(page,group);value=number(text)
                # A box straddling columns is not resolved by its center.
                # OCR boxes include small outer padding; tolerate at most 0.6%
                # page width / 6% cell width, never a substantial column overlap.
                pad=min(.006,(col['x'][1]-col['x'][0])*.06)
                if any(page['words'][i]['bbox'][0]/page['width']<col['x'][0]-pad or (page['words'][i]['bbox'][0]+page['words'][i]['bbox'][2])/page['width']>col['x'][1]+pad for i in group):
                    pending.append({'page':page['page'],'city':city,'year':col['year'],'reason':'数值框跨列边界，需视觉核对'});continue
                rid=unit_identity['id'] if unit_identity else None
                identity=json.dumps([sha,layout_sha,plan_sha,page['page'],city_words,group,col['indicator'],col['year'],city],ensure_ascii=False)
                r={'id':hashlib.sha256(identity.encode()).hexdigest()[:24],'research_id':rid,'source_row_id':hashlib.sha256(json.dumps([sha,page['page'],city_words],ensure_ascii=False).encode()).hexdigest()[:24],'identity_status':'matched' if rid else 'unmapped','city':unit_identity['name'] if unit_identity else city,'year':col['year'],'indicator':col['indicator'],'unit':col['unit'],'value':value,'source_class':source_class,'edition':edition,'geographic_scope':scope_name,'is_derived':False,'evidence':{'kind':'ocr_matrix','file':relative(root,source),'sha256':sha,'ocr_artifact':relative(root,layout_file),'ocr_sha256':layout_sha,'matrix_plan':relative(root,plan_file),'plan_sha256':plan_sha,'parser_version':VERSION,'page':page['page'],'city_words':city_words,'city_text':raw_label,'value_words':group,'value_text':text,'header_refs':col['header_refs'],'scope_refs':spec.get('scope_refs',[]),'scope_text':scope_text,'capture_manifest':relative(root,cap_path),'context_status':context_status},'review_requirements':['原图逐格核对数字、城市、年、单位','脚注行①不能合并或删去','跨页关系及书目类别/版年审核']}
                records.append(r);row_cells+=1
            if not row_cells:pending.append({'page':page['page'],'city':city,'reason':'城市行零有效值，来源仍待核'})
        if not page_rows:pending.append({'page':page['page'],'reason':'该页无可确定城市行；城市列缺失/半行续接不按行号拼接'})
    keyed={}
    for r in records:
        key=(r['city'],r['year'],r['indicator'],r['geographic_scope'])
        if key in keyed:
            pending.append({'code':'OVERLAPPING_OR_CONFLICTING_ROWS','city':r['city'],'year':r['year'],'reason':'跨页重复键或冲突；保留两份证据，必须确认页关系后选择'})
        keyed[key]=r
    return {'records':records,'pending':pending,'skipped':skipped,'source_city_labels':len(labels),'source_rows':row_total,'page_scope':scope,'context_status':context_status,'data_complete':False,'glyph_accuracy_certified':False,'automatic_import_allowed':False,'join_method':'literal city labels with original page anchors; no ordinal or value-based joining'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('input','layout','config','evidence-root','capture-manifest','registry','output'):p.add_argument('--'+n,required=True)
    p.add_argument('--plan');p.add_argument('--propose-plan');a=p.parse_args()
    try:
        config=json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
        if a.propose_plan:
            result=propose(json.loads(Path(a.layout).read_text(encoding='utf-8-sig')),config);save(a.propose_plan,result)
            print(json.dumps({'status':'plan_requires_review','mapped_pages':len(result['pages']),'pending':len(result['proposal_pending']),'note':'补充书目publication并看原图确认页/列/脚注后再提取。'},ensure_ascii=False));return 1 if result['proposal_pending'] else 0
        if not a.plan:raise ValueError('--plan or --propose-plan required')
        result=extract_matrix(a.input,a.layout,a.plan,config,a.evidence_root,a.capture_manifest,json.loads(Path(a.registry).read_text(encoding='utf-8-sig')))
        failed=not result['records'] or bool(result['pending']);status='partial_pending' if result['records'] and failed else 'unparsed' if failed else 'extracted_candidates'
        if result['records']:save(a.output,result['records'])
        save(a.output+'.report.json',{k:v for k,v in result.items() if k!='records'}|{'status':status,'records':len(result['records'])})
        print(json.dumps({'status':status,'records':len(result['records']),'city_labels':result['source_city_labels'],'pending':len(result['pending'])},ensure_ascii=False));return int(failed)
    except Exception as exc:
        result={'status':'unparsed','records':0,'data_complete':False,'failure':classify(exc)};save(a.output+'.report.json',result);print(json.dumps(result,ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
