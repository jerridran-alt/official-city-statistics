"""Progress-aware official downloads: idle timeout, validated Range resume, scoped route."""
import hashlib,json,os,re,time,urllib.request
from pathlib import Path

class DownloadDeferred(TimeoutError):
    """Partial source is retained, never presented as a complete official artifact."""

def atomic_json(path,data):
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(path)

def transfer(url,args,hosts,output,redirect_handler):
    route=getattr(args,'network_route','configured');proxy_env=getattr(args,'proxy_env',None)
    if route not in ('configured','direct','proxy'):raise ValueError('Unknown task network route')
    handlers=[redirect_handler(hosts)]
    if route=='direct':handlers.insert(0,urllib.request.ProxyHandler({}))
    if route=='proxy':
        proxy=os.environ.get(proxy_env or '')
        if not proxy or not re.match(r'^https?://',proxy):raise ValueError('proxy route requires an HTTP(S) endpoint in --proxy-env')
        handlers.insert(0,urllib.request.ProxyHandler({'http':proxy,'https':proxy}))
    opener=urllib.request.build_opener(*handlers)
    key=hashlib.sha256(url.encode()).hexdigest()[:24];output=Path(output);output.mkdir(parents=True,exist_ok=True)
    part=output/(key+'.part');statefile=output/(key+'.part.json');progressfile=output/(key+'.progress.json')
    state=json.loads(statefile.read_text(encoding='utf8')) if part.exists() and statefile.exists() else {}
    offset=0;digest=hashlib.sha256();validator=None
    if state.get('url')==url and getattr(args,'resume',True):
        previous=part.read_bytes()
        if len(previous)!=state.get('bytes') or hashlib.sha256(previous).hexdigest()!=state.get('partial_sha256'):raise ValueError('Partial download changed; preserve and inspect before resuming')
        etag=state.get('etag');validator=etag if etag and not etag.startswith('W/') else state.get('last_modified')
        if validator:offset=len(previous);digest.update(previous)
    headers={'User-Agent':'OfficialStatisticsResearch/1.1','Accept-Encoding':'identity'}
    if offset:headers.update(Range=f'bytes={offset}-',**{'If-Range':validator})
    started=time.monotonic();idle=float(getattr(args,'idle_timeout',None) or args.timeout)
    budget=getattr(args,'max_seconds',None)
    if idle<=0 or (budget is not None and budget<=0):raise ValueError('Timeout/budget must be positive')
    response=opener.open(urllib.request.Request(url,headers=headers),timeout=idle)
    with response:
        from urllib.parse import urlparse
        if urlparse(response.url).hostname not in hosts:raise ValueError('Unregistered final download host')
        code=response.getcode();etag=response.headers.get('ETag');modified=response.headers.get('Last-Modified');length=response.headers.get('Content-Length')
        content_range=response.headers.get('Content-Range','');total=None;resumed=False
        if code==206:
            m=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',content_range)
            if not offset or not m or int(m[1])!=offset or int(m[2])<offset or int(m[2])>=int(m[3]):raise ValueError('Unvalidated partial response; do not append')
            if (state.get('etag') and etag!=state['etag']) or (not state.get('etag') and state.get('last_modified') and modified!=state['last_modified']):raise ValueError('Resume validator changed; do not append')
            total=int(m[3]);resumed=True
        elif code==200:
            offset=0;digest=hashlib.sha256();total=int(length) if length and length.isdigit() else None
        else:raise ValueError('Unexpected download response status')
        if total is not None and total>args.max_bytes:raise ValueError('Response exceeds max-bytes')
        received=offset
        state={'url':url,'final_url':response.url,'etag':etag,'last_modified':modified,'expected_bytes':total}
        def checkpoint(status):
            atomic_json(statefile,{**state,'bytes':received,'partial_sha256':digest.hexdigest(),'complete':False})
            atomic_json(progressfile,{'url':url,'network_route':route,'status':status,'bytes':received,'expected_bytes':total,'resumed_bytes':offset,'seconds':round(time.monotonic()-started,3),'data_complete':False})
        try:
            with part.open('ab' if resumed else 'wb') as stream:
                checkpoint('downloading')
                while True:
                    if total is not None and received==total:break
                    if budget is not None and time.monotonic()-started>=budget:raise DownloadDeferred('User-selected work budget reached; keep partial and resume later')
                    chunk=response.read1(65536)
                    if not chunk:break
                    if received+len(chunk)>args.max_bytes:raise ValueError('Response exceeds max-bytes')
                    stream.write(chunk);stream.flush();digest.update(chunk);received+=len(chunk);checkpoint('downloading')
            if total is not None and received!=total:raise DownloadDeferred('Incomplete body; retain validated partial, do not publish')
        except Exception:
            checkpoint('partial_deferred');raise
        body=part.read_bytes();checkpoint('download_complete_pending_manifest')
        return body,response.url,response.headers,{'network_route':route,'resumed_bytes':offset,'download_seconds':round(time.monotonic()-started,3),'partial_path':str(part),'partial_state_path':str(statefile),'progress_path':str(progressfile)}

def committed(meta):
    # Only after the original blob and complete capture manifest are durable.
    for name in ('partial_path','partial_state_path'):
        Path(meta[name]).unlink(missing_ok=True)
    p=Path(meta['progress_path']);state=json.loads(p.read_text(encoding='utf8'));state.update(status='captured_complete',source_complete=True,data_complete=False);atomic_json(p,state)
