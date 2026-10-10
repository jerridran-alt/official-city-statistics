"""Compare task-scoped routes on one official URL; never change global VPN/OS settings."""
import argparse,json,time
from pathlib import Path
from types import SimpleNamespace
from official_fetch import fetch,write_json
from network_health import failure

def probe(url,registry,output,routes=('configured','direct'),idle_timeout=5,work_budget=10,proxy_env=None):
    output=Path(output);results=[]
    for route in routes:
        begin=time.monotonic()
        args=SimpleNamespace(url=url,registry=str(registry),output=str(output/route),network_state=str(output/'health'),engine='http',html=None,refresh=True,encoding=None,retries=0,timeout=idle_timeout,idle_timeout=idle_timeout,max_seconds=work_budget,max_bytes=2*1024*1024,network_route=route,proxy_env=proxy_env,resume=True)
        try:
            capture=fetch(args);results.append({'route':route,'status':'ok','bytes':capture['bytes'],'sha256':capture['sha256'],'title':capture.get('document_title'),'cache_hit':capture.get('cache_hit',False),'seconds':round(time.monotonic()-begin,3)})
        except Exception as exc:results.append({'route':route,'status':'failed','failure':failure(exc),'seconds':round(time.monotonic()-begin,3)})
    report={'url':url,'results':results,'global_settings_changed':False,'vpn_state_not_modified':True,'outbound_region':'not measured','direct_route_limit':'Bypasses HTTP/system proxy for this request only; VPN TUN/full-tunnel routing may still intercept it. A successful probe proves access, not IP geolocation.'}
    write_json(output/'route_report.json',report);return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('url','registry','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--routes',default='configured,direct');p.add_argument('--idle-timeout',type=float,default=5);p.add_argument('--work-budget',type=float,default=10);p.add_argument('--proxy-env');a=p.parse_args()
    r=probe(a.url,a.registry,a.output,a.routes.split(','),a.idle_timeout,a.work_budget,a.proxy_env)
    print(json.dumps(r,ensure_ascii=False));return 0 if any(x['status']=='ok' for x in r['results']) else 1
if __name__=='__main__':raise SystemExit(main())
