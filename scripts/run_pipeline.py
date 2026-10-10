"""Official article/image → candidate evidence. No silent zero and no automatic approval."""
import argparse,hashlib,json,time
from pathlib import Path
from types import SimpleNamespace
from official_fetch import fetch
from document_extract import extract_article
from ocr_layout import run_ocr
from ocr_extract import extract_ocr
from audit_candidates import audit
from stats_core import save
from failure_types import classify,SourceFailure
from validation_coverage import coverage
from execution_control import PhaseLedger


def run(url,config,registry_file,output,media_limit=2,ocr_engine='auto',parent_url=None,matrix_plan=None):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True);started=time.monotonic();capture_dir=output/'capture'
    ledger=PhaseLedger(output/'phase_ledger.json')
    def timed(phase,fn,*args,**kwargs):
        begin=time.time();status='failed'
        try:
            result=fn(*args,**kwargs);status='ok';return result
        finally:ledger.record(phase,begin,status)
    registry=json.loads(Path(registry_file).read_text(encoding='utf-8-sig'))
    net=config.get('network',{})
    args=SimpleNamespace(url=url,registry=str(Path(registry_file).resolve()),output=str(capture_dir),html=None,refresh=False,encoding=None,retries=0,timeout=net.get('idle_timeout',25),max_bytes=100*1024*1024,engine='http',network_route=net.get('route','configured'),proxy_env=net.get('proxy_env'),max_seconds=net.get('work_budget_seconds'),resume=True)
    cap=timed('network',fetch,args);manifest=capture_dir/(hashlib.sha256((url+'\0http').encode()).hexdigest()[:24]+'.json');source=capture_dir/cap['file']
    with source.open('rb') as f:prefix=f.read(8)
    if prefix.startswith(b'%PDF') or cap['content_type'].lower().startswith('image/'):
        if prefix.startswith(b'%PDF'):
            from pdf_probe import probe
            pdf_sample=timed('parse',probe,source);save(output/'pdf_probe.json',pdf_sample)
            if pdf_sample['total_pages']>5 and not matrix_plan:
                raise SourceFailure('PDF_TARGET_PAGES_REQUIRED','长PDF已抽查正文；先核对目录和原页码，提供矩阵页映射，不默认OCR前5页或全文穷搜')
        parent_manifest=None
        if parent_url:
            parent_args=SimpleNamespace(**vars(args));parent_args.url=parent_url;timed('network',fetch,parent_args)
            parent_manifest=capture_dir/(hashlib.sha256((parent_url+'\0http').encode()).hexdigest()[:24]+'.json')
        if matrix_plan:
            from ocr_matrix import extract_matrix
            plan=json.loads(Path(matrix_plan).read_text(encoding='utf-8-sig'));save(output/'matrix_plan.json',plan)
            selected_pages=plan.get('page_scope') if prefix.startswith(b'%PDF') else None
            if prefix.startswith(b'%PDF') and pdf_sample['total_pages']>5 and not selected_pages:
                raise SourceFailure('PDF_TARGET_PAGES_REQUIRED','长PDF矩阵映射须明确page_scope原页码，不能默认第一页')
            if selected_pages and len(selected_pages)>100:raise ValueError('Matrix page limit exceeded')
            layout,artifact,reused=timed('ocr',run_ocr,source,output/'ocr_cache',ocr_engine,max_pages=max(1,len(selected_pages or [1])),page_numbers=selected_pages)
            extracted=timed('parse',extract_matrix,source,artifact,output/'matrix_plan.json',config,output,manifest,registry)
        else:
            layout,artifact,reused=timed('ocr',run_ocr,source,output/'ocr_cache',ocr_engine)
            extracted=timed('parse',extract_ocr,source,artifact,config,output,manifest,registry,parent_manifest)
        records=extracted['records']
        if not records:raise SourceFailure('OCR_LAYOUT_UNPARSED','PDF/图片已OCR但未得到可确定原数；需视觉或另一版式后端，不得喂空数据')
        save(output/'candidates.json',records);save(output/'candidates.json.report.json',{'status':'partial_pending' if extracted['pending'] else 'extracted_candidates','records':len(records),'data_complete':False});report=timed('machine_audit',audit,records,config,output,registry);save(output/'audit.json',report)
        result={'status':'partial_pending' if extracted['pending'] else 'candidates_require_review','records':len(records),'machine_checks_passed':report['machine_checks_passed'],'unreviewed':len(records),'image_sources_queued':layout['pages_queued'],'failed_sources':[],'seconds':round(time.monotonic()-started,3),'data_complete':False,'backend':'mapped matrix OCR' if matrix_plan else 'PDF/image OCR','pending':extracted['pending'],'validation_coverage':coverage()};result['timing']=ledger.summary();save(output/'pipeline_report.json',result);return result
    if matrix_plan:raise SourceFailure('MATRIX_DIRECT_ATTACHMENT_REQUIRED','矩阵计划需要直接官方PDF/图片URL；当前是HTML，不静默改走单城正文路径')
    article=timed('parse',extract_article,source,config,output,manifest);records=article['records'];media=[];failures=[]
    # The limit bounds work, not a claim that unvisited image sources are empty.
    relevant=[i for i in article['images'] if '表' in i['preceding_text'][-180:] and any(k in i['preceding_text'][-400:] for k in ('生产总值','人口','贷款','能源','用电'))]
    for image in relevant[:media_limit]:
        try:
            args.url=image['url'];capture=timed('network',fetch,args);image_manifest=capture_dir/(hashlib.sha256((image['url']+'\0http').encode()).hexdigest()[:24]+'.json');image_file=capture_dir/capture['file']
            layout,artifact,reused=timed('ocr',run_ocr,image_file,output/'ocr_cache',ocr_engine)
            extracted=timed('parse',extract_ocr,image_file,artifact,config,output,image_manifest,registry,manifest)
            records.extend(extracted['records']);media.append({'url':image['url'],'records':len(extracted['records']),'ocr_seconds':layout['seconds'],'cache_reused':reused,'pending':extracted['pending']})
            if not extracted['records']:failures.append({'url':image['url'],'failure':{'code':'OCR_LAYOUT_UNPARSED','category':'parse','retryable':False,'reason':'OCR 已产生词，但没有可确定的指标行；需视觉/其他布局后端'}})
        except Exception as exc:failures.append({'url':image['url'],'failure':classify(exc)})
    if not records:raise SourceFailure('NO_CANDIDATES','所有路径均未取得指标记录，来源未解析，非数据齐全')
    save(output/'candidates.json',records);save(output/'candidates.json.report.json',{'status':'extracted_candidates','records':len(records),'data_complete':False});report=timed('machine_audit',audit,records,config,output,registry);save(output/'audit.json',report)
    result={'status':'candidates_require_review','records':len(records),'machine_checks_passed':report['machine_checks_passed'],'unreviewed':len(records),'image_results':media,'failed_sources':failures,'image_sources_queued':max(0,len(relevant)-media_limit),'unsupported_rules':article['unsupported_rules'],'missing_indicators':[n for n in config['keep_indicators'] if n not in {r['indicator'] for r in records}],'excluded_mentions':article['excluded_mentions'],'seconds':round(time.monotonic()-started,3),'data_complete':False,'note':'候选生成不是统计真实性认证。先完成原文/原图和口径审核，再运行 select_panel.py。'}
    result['validation_coverage']=coverage()
    result['timing']=ledger.summary();save(output/'pipeline_report.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('url','config','registry','output'):p.add_argument('--'+n,required=True)
    p.add_argument('--media-limit',type=int,default=2);p.add_argument('--ocr-engine',choices=('auto','windows','rapidocr','tesseract'),default='auto');p.add_argument('--parent-url');p.add_argument('--matrix-plan',help='Reviewed page/column mapping for a direct PDF/image; source/plan hashes remain review-bound');a=p.parse_args()
    # Parent URL supplies verified title/year context for a directly addressed attachment.
    try:
        if not 0<=a.media_limit<=20:raise ValueError('media-limit must be 0..20')
        config=json.loads(Path(a.config).read_text(encoding='utf-8-sig'));result=run(a.url,config,a.registry,a.output,a.media_limit,a.ocr_engine,getattr(a,'parent_url',None),getattr(a,'matrix_plan',None))
        print(json.dumps({k:result[k] for k in ('status','records','machine_checks_passed','unreviewed','image_sources_queued','seconds','data_complete')},ensure_ascii=False))
        return 1 if result['failed_sources'] or not result['machine_checks_passed'] else 0
    except Exception as exc:
        result={'status':'unparsed','records':0,'failure':classify(exc),'data_complete':False}
        ledger_path=Path(a.output)/'phase_ledger.json'
        if ledger_path.exists():result['timing']=PhaseLedger(ledger_path).summary()
        save(Path(a.output)/'pipeline_report.json',result);save(Path(a.output)/'candidates.json.report.json',result);print(json.dumps(result,ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
