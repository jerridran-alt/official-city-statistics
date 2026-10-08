"""Directory-first access for configured provinces; no invented yearbook paths."""
import argparse,json,re,time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
from official_fetch import fetch
from failure_types import classify

def discover(profile,registry,output,network_state=None,follow_years=0,timeout=10,discovery_seconds=120):
    if discovery_seconds <= 0:raise ValueError('discovery_seconds must be positive')
    deadline=time.monotonic()+discovery_seconds;budget_exhausted=False
    seeds=profile.get('catalog_urls') or [profile['portal_url']]
    hosts={r['host'] for r in json.loads(Path(registry).read_text(encoding='utf8'))['hosts'] if r.get('verified')}
    results=[];years={};pending=[];queue=list(dict.fromkeys(seeds));fallback=list(profile.get('fallback_catalog_urls',[]));seen=set();limit=profile.get('discovery_page_limit',4)
    for _ in range(limit):
        if time.monotonic()>=deadline:budget_exhausted=True;break
        if not queue and not years:
            queue=[u for u in fallback if u not in seen];fallback=[]
        if not queue:break
        url=queue.pop(0)
        if url in seen:continue
        seen.add(url)
        try:
            r=fetch(SimpleNamespace(url=url,registry=registry,output=output,network_state=network_state,engine='http',html=None,refresh=False,encoding=None,retries=0,timeout=timeout,max_bytes=20000000,wait_selector=None))
            results.append({'url':url,'final_url':r['final_url'],'status':'ok','sha256':r['sha256'],'cache_hit':r.get('cache_hit',False),'encoding':r.get('encoding')})
            title=r.get('document_title','');edition=re.search(r'(?:19|20)\d{2}',title);book_context='年鉴' in title or 'Yearbook' in title
            if profile.get('entry_kind')=='direct_yearbook' and url in seeds and edition and ('年鉴' in title or 'Yearbook' in title):
                years[(int(edition.group()),r['final_url'])]={'edition':int(edition.group()),'url':r['final_url'],'title':title,'discovered_from':r['final_url'],'source_sha256':r['sha256'],'discovery':'original_document_title'}
            for a in r['links']:
                if urlparse(a['url']).hostname not in hosts:continue
                if a['url'].split('#')[0]==r['final_url'].split('#')[0]:continue
                title=a['text'];match=re.search(r'(?:19|20)\d{2}',title)
                year_only=bool(re.fullmatch(r'\s*(?:19|20)\d{2}\s*(?:年|版)?\s*',title))
                if year_only and (not book_context or 'search' in urlparse(a['url']).path.lower()):
                    pending.append({**a,'discovered_from':r['final_url'],'reason':'单独年份或搜索筛选链接无明确年鉴书目上下文，待核'});continue
                if match and ('年鉴' in title or 'Yearbook' in title or (book_context and year_only)):
                    years[(int(match.group()),a['url'])]={'edition':int(match.group()),'url':a['url'],'title':title,'discovered_from':r['final_url'],'source_sha256':r['sha256'],'discovery':a.get('discovery','anchor_href')}
                elif '年鉴' in title or a.get('is_catalog_frame'):
                    queue.append(a['url'])
        except Exception as e:results.append({'url':url,'status':'deferred' if getattr(e,'code',None)=='HOST_DEFERRED' else 'failed','failure':classify(e)})
    entries=sorted(years.values(),key=lambda x:x['edition'],reverse=True);verified=[]
    for entry in entries[:follow_years]:
        if time.monotonic()>=deadline:budget_exhausted=True;break
        try:
            r=fetch(SimpleNamespace(url=entry['url'],registry=registry,output=output,network_state=network_state,engine='http',html=None,refresh=False,encoding=None,retries=0,timeout=timeout,max_bytes=20000000,wait_selector=None))
            verified.append({**entry,'status':'ok','final_url':r['final_url'],'source_sha256':r['sha256'],'frames':[a['url'] for a in r['links'] if a.get('is_catalog_frame')]})
        except Exception as e:verified.append({**entry,'status':'failed','failure':classify(e)})
    report={'province':profile['province'],'catalog_pages':results,'yearbook_entries':entries,'pending_year_links':pending,'visited_yearbooks':verified,'unvisited_catalog_urls':queue,'unvisited_yearbook_entries':entries[len(verified):],'discovery_budget_seconds':discovery_seconds,'budget_exhausted':budget_exhausted,'data_complete':False,'scope':'Configured official catalog links only; discovered entries are not all claimed reachable','checked_unix':time.time()}
    Path(output).mkdir(parents=True,exist_ok=True);(Path(output)/'province_access_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--profiles',required=True);p.add_argument('--province',required=True);p.add_argument('--registry',required=True);p.add_argument('--output',required=True);p.add_argument('--network-state');p.add_argument('--follow-years',type=int,default=0);p.add_argument('--timeout',type=float,default=10);p.add_argument('--discovery-seconds',type=float,default=120);a=p.parse_args()
    if not 0<=a.follow_years<=5 or not 0<a.timeout<=30:p.error('Bound follow-years to 0..5 and timeout to 0..30')
    profiles=json.loads(Path(a.profiles).read_text(encoding='utf8'));profile=next(x for x in profiles['provinces'] if x['province']==a.province)
    r=discover(profile,a.registry,a.output,a.network_state,a.follow_years,a.timeout,a.discovery_seconds);print(json.dumps({'province':r['province'],'directory_pages':len(r['catalog_pages']),'yearbooks_discovered':len(r['yearbook_entries']),'yearbooks_checked':len(r['visited_yearbooks'])},ensure_ascii=False))
    return 0 if r['yearbook_entries'] and not r['budget_exhausted'] else 1
if __name__=='__main__':raise SystemExit(main())
