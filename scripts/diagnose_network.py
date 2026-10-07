"""Read-only DNS and current-route HTTP diagnostics; no proxy or TLS configuration changes."""
import argparse,json,socket,time,urllib.request,urllib.error
from urllib.parse import urlparse
from pathlib import Path
from network_health import failure

def probe(url,timeout=8):
    host=urlparse(url).hostname;result={'url':url,'outbound_region':'unknown','current_proxy_config_present':bool(urllib.request.getproxies()),'route':'current configured route; unchanged'}
    start=time.monotonic()
    try:result['dns_addresses']=sorted({r[4][0] for r in socket.getaddrinfo(host,None)})
    except OSError as e:result['dns_failure']=failure(e)
    result['dns_seconds']=round(time.monotonic()-start,3)
    start=time.monotonic()
    try:
        # Ordinary request with the user's existing route and certificate verification.
        req=urllib.request.Request(url,headers={'User-Agent':'OfficialStatisticsResearch/1.0'})
        with urllib.request.urlopen(req,timeout=timeout) as r:
            result.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type'),sample_bytes=len(r.read(1024)))
    except Exception as e:result.update(failure=failure(e),error=str(e))
    result['request_seconds']=round(time.monotonic()-start,3)
    result['conclusion']='Timeout alone does not establish overseas IP blocking; compare authorized routes or publisher response before attributing location.'
    return result
def main():
    p=argparse.ArgumentParser();p.add_argument('--url',action='append',required=True);p.add_argument('--output',required=True);p.add_argument('--timeout',type=float,default=8);a=p.parse_args()
    if len(a.url)>4 or not 0<a.timeout<=30:p.error('At most four representative endpoints; timeout 0..30 seconds')
    for u in a.url:
        x=urlparse(u)
        if x.scheme not in ('http','https') or x.username or x.password:p.error('HTTP(S) without embedded credentials required')
    results=[probe(u,a.timeout) for u in a.url];Path(a.output).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(results,ensure_ascii=False))
if __name__=='__main__':main()
