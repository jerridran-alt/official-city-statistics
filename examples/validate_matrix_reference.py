"""Replay archived real-source OCR cases; local input never impersonates a fresh network capture."""
import argparse,hashlib,json,sys,shutil,time
from pathlib import Path
SKILL=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SKILL/'scripts'))
from ocr_layout import run_ocr
from ocr_matrix import propose,extract_matrix
from audit_candidates import audit
from stats_core import save,norm

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=('hebei','cq'),required=True);p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    start=time.perf_counter();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=True)
    ref=json.loads((SKILL/'examples'/('hebei_matrix_reference.json' if a.case=='hebei' else 'cq_crosspage_reference.json')).read_text(encoding='utf8'))
    source=Path(a.input).resolve()
    if hashlib.sha256(source.read_bytes()).hexdigest()!=ref['source_sha256']:raise ValueError('Original source changed; re-review rather than accepting this fixed reference case')
    local=out/'source.bin'
    if source!=local:shutil.copyfile(source,local)
    publisher='河北省统计局' if a.case=='hebei' else '重庆市统计局';host='tjj.hebei.gov.cn' if a.case=='hebei' else 'tjj.cq.gov.cn'
    registry={'hosts':[{'host':host,'publisher':publisher,'publisher_id':a.case+'-statistics','level':'province','evidence_url':'https://'+host+'/','verified':True}]}
    save(out/'authorities.json',registry)
    cap={'url':ref['source_url'],'final_url':ref['source_url'],'file':'source.bin','sha256':ref['source_sha256'],'bytes':local.stat().st_size,'publisher':publisher,'mode':'archived_original','note':'User-supplied original archive, not a fresh network capture or automatic import authorization'}
    save(out/'capture.json',cap)
    if a.case=='hebei':
        config={'years':[2015,2024],'units':[{'id':'demo:石家庄市','name':'石家庄市','aliases':[]},{'id':'demo:廊坊市','name':'廊坊市','aliases':[]}],'keep_indicators':['全社会用电量']}
        layout,artifact,reused=run_ocr(local,out/'ocr_cache','rapidocr',scale=3)
        plan=propose(layout,config);plan['publication']={'edition':2025,'source_class':'yearbook'}
        page=layout['pages'][0]
        plan['pages'][0]['scope_refs']=[[page['page'],i] for i,w in enumerate(page['words']) if '含辛集' in w['text'] or '以下相关表同' in w['text']]
        expected={(n,y,'全社会用电量'):v for n,values in ref['rows'].items() for y,v in zip(ref['years'],values)}
    else:
        config={'years':[2024,2024],'units':[],'keep_indicators':['户籍人口','年末常住人口'],'indicator_aliases':{'户籍人口':['年末总人口'],'年末常住人口':['常住人口']}}
        layout,artifact,reused=run_ocr(local,out/'ocr_cache','rapidocr',scale=2,max_pages=2,page_numbers=[593,596])
        pages={v['page']:v for v in layout['pages']}
        def anchor(pn,label,x=None):
            pg=pages[pn];found=[i for i,w in enumerate(pg['words']) if norm(label) in norm(w['text']) and (x is None or x[0]<=(w['bbox'][0]+w['bbox'][2]/2)/pg['width']<x[1])]
            if len(found)!=1:raise ValueError('Original anchor is missing/ambiguous: '+str((pn,label,found)))
            return [pn,found[0]]
        title=anchor(593,'20-1');continued=anchor(596,'20-1')
        ignore=['主城都市区','中心城区','渝西地区','渝东新城','渝东北三峡库区','渝东南武陵山区']
        plan={'version':'1.0','source_sha256':ref['source_sha256'],'page_scope':[593,596],'explicit_table_page_subset':True,'publication':{'edition':2025,'source_class':'yearbook','document_page':3,'document_quote':'《重庆统计年鉴2025》'},'pages':[
            {'page':593,'table_key':'20-1','table_refs':[title],'city_x':[.09,.26],'body_y':[.25,.93],'skip_city_labels':ignore,'scope':'原表城市行','scope_refs':[],'columns':[{'indicator':'户籍人口','year':2024,'unit':'万人','x':[.598,.699],'header_refs':[title,anchor(593,'年末总人口'),anchor(593,'万人',[.598,.699])]}]},
            {'page':596,'table_key':'20-1','table_refs':[continued],'continues_page':593,'city_x':[.09,.26],'body_y':[.22,.93],'skip_city_labels':ignore,'scope':'原表城市行','scope_refs':[],'columns':[{'indicator':'年末常住人口','year':2024,'unit':'万人','x':[.697,.796],'header_refs':[title,anchor(596,'常住人口'),anchor(596,'万人',[.697,.796])]}]}
        ]}
        expected={(r['city'],2024,r['indicator']):r['value'] for r in ref['records']}
    config['source_priorities']=[{'name':'省年鉴','match':{'source_class':'yearbook'}}];save(out/'project.json',config);save(out/'matrix_plan.json',plan)
    result=extract_matrix(local,artifact,out/'matrix_plan.json',config,out,out/'capture.json',registry)
    save(out/'candidates.json',result['records']);save(out/'matrix_report.json',{k:v for k,v in result.items() if k!='records'})
    actual={(r['city'],r['year'],r['indicator']):r['value'] for r in result['records']}
    if actual!=expected or result['pending']:raise ValueError('Reference mismatch or unresolved cells: inspect original source, do not silently change reference')
    checked=audit(result['records'],config,out,registry);save(out/'audit.json',checked)
    if not checked['machine_checks_passed']:raise ValueError('Original source/plan replay failed')
    report={'case':a.case,'status':'archived_reference_case_passed','records':len(result['records']),'source_city_labels':result['source_city_labels'],'reference_exact_matches':len(expected),'pages':result['page_scope'],'ocr_engine':layout['profile']['engine'],'ocr_seconds':layout['seconds'],'cache_reused':reused,'seconds':round(time.perf_counter()-start,3),'network_provenance_available':False,'automatic_import_allowed':False,'glyph_accuracy_certified':False,'data_complete':False,'master_panel_modified':False}
    save(out/'validation_report.json',report);print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
