"""Bounded host circuit; no proxy changes, TLS bypass or location inference."""
import hashlib,json,time,socket,ssl,urllib.error
from pathlib import Path
from contextlib import contextmanager

class HostDeferred(ConnectionError):
    def __init__(self,host,until,reason):
        super().__init__(f'{host}: deferred until {until}: {reason}')
        self.retry_after=until;self.code='HOST_DEFERRED'

def failure(exc):
    cause=getattr(exc,'reason',exc)
    if isinstance(exc,urllib.error.HTTPError):
        status=exc.code
        return {'code':f'HTTP_{status}','host_failure':status in (403,408,412,429,500,502,503,504),'immediate':status in (403,412,429),'retryable':status in (408,429,500,502,503,504)}
    if isinstance(cause,socket.gaierror):code='DNS_ERROR'
    elif isinstance(cause,ssl.SSLCertVerificationError):code='TLS_CERTIFICATE_ERROR'
    elif 'handshake' in str(cause).lower():code='TLS_HANDSHAKE_TIMEOUT'
    elif isinstance(cause,ssl.SSLError):code='TLS_ERROR'
    elif isinstance(cause,(TimeoutError,socket.timeout)):code='NETWORK_TIMEOUT'
    elif isinstance(cause,ConnectionError):code='CONNECTION_ERROR'
    elif isinstance(exc,urllib.error.URLError):code='TRANSPORT_ERROR'
    else:return {'code':'OTHER_ERROR','host_failure':False,'immediate':False,'retryable':False}
    return {'code':code,'host_failure':True,'immediate':False,'retryable':code!='TLS_CERTIFICATE_ERROR'}

@contextmanager
def host_slot(directory,host,wait=30):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256(host.encode()).hexdigest()[:24];lock=directory/(key+'.lock');statefile=directory/(key+'.json');end=time.monotonic()+wait
    while True:
        try:lock.mkdir();break
        except FileExistsError:
            if time.monotonic()>=end:raise HostDeferred(host,time.time()+wait,'host already has an active probe; queue later')
            time.sleep(.05)
    try:
        state=json.loads(statefile.read_text(encoding='utf8')) if statefile.exists() else {'consecutive_failures':0,'deferred_until':0}
        if state.get('deferred_until',0)>time.time():raise HostDeferred(host,state['deferred_until'],'host circuit open; use official cache or alternate source')
        yield state,statefile
    finally:lock.rmdir()

def finish(state,path,exc=None,threshold=2,cooldown=900):
    if exc is None:state.update(consecutive_failures=0,deferred_until=0,last_outcome='ok')
    else:
        f=failure(exc);state['last_outcome']=f['code']
        if f['host_failure']:
            state['consecutive_failures']=state.get('consecutive_failures',0)+1
            if f['immediate'] or state['consecutive_failures']>=threshold:
                delay=cooldown
                if isinstance(exc,urllib.error.HTTPError):
                    retry=exc.headers.get('Retry-After','') if exc.headers else ''
                    if retry.isdigit():delay=max(delay,int(retry))
                state['deferred_until']=time.time()+delay
    state['checked_at']=time.time();tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2),encoding='utf8');tmp.replace(path)
