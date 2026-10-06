"""Real official multi-city HTML example. Run from any directory with --output."""
import argparse,json,sys,time
from pathlib import Path
SKILL=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
from official_fetch import fetch
from extract_tables import execute
from audit_candidates import audit
from select_panel import select
from stats_core import save

def run(output):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
    registry={'hosts':[{'host':'tj.jiangsu.gov.cn','publisher':'江苏省统计局','publisher_id':'jiangsu-statistics','level':'province','evidence_url':'https://tj.jiangsu.gov.cn/col/col93166/index.html','verified':True}]}
    save(out/'authorities.json',registry)
    urls=['https://tj.jiangsu.gov.cn/2025/indexc.htm','https://tj.jiangsu.gov.cn/2025/nj09.htm','https://tj.jiangsu.gov.cn/2025/nj09/nj0910.htm']
    manifests=[];captures=[]
    for url in urls:
        r=fetch(argparse.Namespace(url=url,registry=str(out/'authorities.json'),output=str(out/'capture'),engine='http',refresh=False,html=None,timeout=25,retries=0,max_bytes=5000000,encoding=None,wait_selector=None))
        captures.append(r)
        found=[p for p in (out/'capture').glob('*.json') if json.loads(p.read_text(encoding='utf8')).get('final_url')==url]
        if len(found)!=1:raise ValueError('Ambiguous capture manifest')
        manifests.append(found[0].relative_to(out).as_posix())
    reference=json.loads((SKILL/'examples/jiangsu_reference.json').read_text(encoding='utf8'))
    if captures[-1]['sha256']!=reference['source_sha256']:raise ValueError('Official source changed: re-review rather than updating reference automatically')
    names=['南京市','无锡市','徐州市','常州市','苏州市','南通市','连云港市','淮安市','盐城市','扬州市','镇江市','泰州市','宿迁市']
    # Full names are only demo identities, not guessed administrative codes.
    units=[{'id':'demo:'+n,'name':n,'aliases':[]} for n in names]
    config={'years':[2018,2024],'units':units[:2],'keep_indicators':['全社会用电量'],'source_priorities':[{'name':'各省统计年鉴','match':{'authority_level':'province','source_class':'yearbook'}}]}
    save(out/'project.json',config)
    note='注：各市及分区域用电量中，未包括主网网损、统调公用电厂厂用电量和租赁制抽蓄电站耗用量。(下同)'
    mapping={'source_class':'yearbook','edition':2025,'class_quote':'《江苏统计年鉴》2025','edition_quote':'《江苏统计年鉴》2025','context_chain':manifests[:2],'tables':[{'table_index':0,'city_column':0,'data_start_row':6,'scope':'各市','scope_quote':note,'skip_row_labels':['全省','苏南','苏中','苏北','注：','The electricity'],'columns':[{'column':i+2,'indicator':'全社会用电量','year':y,'unit':'亿千瓦时','header_cells':[[0,0],[3,0],[4,i+2]]} for i,y in enumerate(reference['years'])]}]}
    save(out/'mapping.json',mapping)
    args=argparse.Namespace(input=str(out/'capture'/captures[-1]['file']),format='html',config=str(out/'project.json'),mapping=str(out/'mapping.json'),output=str(out/'candidates.json'),cache_dir=str(out/'table_cache'),evidence_root=str(out),capture_manifest=str(out/manifests[-1]),encoding='utf-8')
    if execute(args):raise ValueError('First extraction failed')
    first=json.loads((out/'candidates.json.report.json').read_text(encoding='utf8'))
    records=json.loads((out/'candidates.json').read_text(encoding='utf8'))
    assert len(records)==91 and first['source_cities_extracted']==13 and first['research_units_matched']==2
    assert len([r for r in records if r['research_id'] is None])==77
    audit_first=audit(records,config,out,registry);assert audit_first['passed']==91
    config['units']=units;save(out/'project_all.json',config);args.config=str(out/'project_all.json');args.output=str(out/'candidates_all.json')
    if execute(args):raise ValueError('Cached expanded-sample extraction failed')
    second=json.loads((out/'candidates_all.json.report.json').read_text(encoding='utf8'))
    assert second['source_table_cache_reused'] and second['research_units_matched']==13
    records=json.loads((out/'candidates_all.json').read_text(encoding='utf8'))
    assert {(r['city'],r['year']):r['value'] for r in records}=={(n,y):v for n,values in reference['rows'].items() for y,v in zip(reference['years'],values)}
    report=audit(records,config,out,registry);save(out/'audit.json',report);assert report['passed']==91
    # Session-reviewed reference replay is named honestly; this is not a human sign-off.
    reviews=[{'record_id':r['id'],'source_sha256':r['evidence']['sha256'],'decision':'approve','reviewer':'Codex reference replay of session-reviewed original HTML cells','reason':note+'；与已逐格复核的真实参考值一致。范围是各市，不替换成含网损的省合计；demo ID不用于正式研究匹配。'} for r in records]
    save(out/'reference_reviews.json',reviews)
    selected=select(records,config,report,reviews);save(out/'selected.json',selected)
    assert len(selected['selected'])==91 and not selected['pending'] and not selected['conflicts']
    result={'status':'reference_case_passed','source':urls[-1],'format':'original_html','cities':13,'years':[2018,2024],'original_values':91,'first_pass_research_cities':2,'first_pass_out_of_sample_values_preserved':77,'expanded_sample_cache_reused':True,'audit_passed':91,'selected_reference_values':91,'original_table_parses_in_extraction':1 if not first['source_table_cache_reused'] else 0,'audit_reloads_original':True,'fetch_cache_hits':sum(bool(r.get('cache_hit')) for r in captures),'seconds':round(time.perf_counter()-start,3),'scope_note':note,'review_type':'session-reviewed reference regression, not independent human sign-off','data_complete':False,'master_research_panel_modified':False,'not_validated':['多城市扫描矩阵','复杂跨页表','其他省份及未知布局']}
    save(out/'validation_report.json',result);print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    run(p.parse_args().output)
