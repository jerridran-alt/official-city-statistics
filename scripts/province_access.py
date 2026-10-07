"""Directory-first access for configured provinces; no invented yearbook paths."""
import argparse,json,re,time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
from official_fetch import fetch
from failure_types import classify

def discover(profile,registry,output,network_state=None,follow_years=0,timeout=10):
    seeds=profile.get('catalog_urls') or [profile['portal_url']]
    hosts={r['host'] for r in json.loads(Path(registry).read_text(encoding='utf8'))['hosts'] if r.get('verified')}
    results=[];years={};queue=list(dict.fromkeys(seeds));seen=set();limit=profile.get('discovery_page_limit',4)
    for _ in range(limit):
        if not queue:break
        url=queue.pop(0)
        if url in seen:continue
        seen.add(url)
        try:
            r=fetch(SimpleNamespace(url=url,registry=registry,output=output,network_state=network_state,engine='http',html=None,refresh=False,encoding=None,retries=0,timeout=timeout,max_bytes=20000000,wait_selector=None))
            results.append({'url':url,'final_url':r['final_url'],'status':'ok','sha256':r['sha256'],'cache_hit':r.get('cache_hit',False),'encoding':r.get('encoding')})
            for a in r['links']:
                if urlparse(a['url']).hostname not in hosts:continue
                title=a['text'];match=re.search(r'(?:19|20)\d{2}',title)
                if match and ('年鉴' in title or 'Yearbook' in title):
                    years[(int(match.group()),a['url'])]={'edition':int(match.group()),'url':a['url'],'title':title,'discovered_from':r['final_url'],'source_sha256':r['sha256'],'discovery':a.get('discovery','anchor_href')}
                elif '年鉴' in title or a.get('is_catalog_frame'):queue.append(a['url'])
        except Exception as e:results.append({'url':url,'status':'deferred' if getattr(e,'code',None)=='HOST_DEFERRED' else 'failed','failure':classify(e)})
    entries=sorted(years.values(),key=lambda x:x['edition'],reverse=True);verified=[]
    for entry in entries[:follow_years]:
        try:
            r=fetch(SimpleNamespace(url=entry['url'],registry=registry,output=output,network_state=network_state,engine='http',html=None,refresh=False,encoding=None,retries=0,timeout=timeout,max_bytes=20000000,wait_selector=None))
            verified.append({**entry,'status':'ok','final_url':r['final_url'],'source_sha256':r['sha256'],'frames':[a['url'] for a in r['links'] if a.get('is_catalog_frame')]})
        except Exception as e:verified.append({**entry,'status':'failed','failure':classify(e)})
    report={'province':profile['province'],'catalog_pages':results,'yearbook_entries':entries,'visited_yearbooks':verified,'unvisited_catalog_urls':queue,'scope':'Configured official catalog links only; discovered entries are not all claimed reachable','checked_unix':time.time()}
    Path(output).mkdir(parents=True,exist_ok=True);(Path(output)/'province_access_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--profiles',required=True);p.add_argument('--province',required=True);p.add_argument('--registry',required=True);p.add_argument('--output',required=True);p.add_argument('--network-state');p.add_argument('--follow-years',type=int,default=0);p.add_argument('--timeout',type=float,default=10);a=p.parse_args()
    if not 0<=a.follow_years<=5 or not 0<a.timeout<=30:p.error('Bound follow-years to 0..5 and timeout to 0..30')
    profiles=json.loads(Path(a.profiles).read_text(encoding='utf8'));profile=next(x for x in profiles['provinces'] if x['province']==a.province)
    r=discover(profile,a.registry,a.output,a.network_state,a.follow_years,a.timeout);print(json.dumps({'province':r['province'],'directory_pages':len(r['catalog_pages']),'yearbooks_discovered':len(r['yearbook_entries']),'yearbooks_checked':len(r['visited_yearbooks'])},ensure_ascii=False))
    return 0 if r['yearbook_entries'] else 1
if __name__=='__main__':raise SystemExit(main())
