"""Validate captured publication-to-table navigation without modifying original HTML."""
import hashlib,json,re
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin,urlparse

class ContextHTML(HTMLParser):
    def __init__(self,url):
        super().__init__();self.url=url;self.links=set();self.text=[];self.ignore=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style'):self.ignore+=1
        for key in ('href','src'):
            if a.get(key):self.links.add(urljoin(self.url,a[key]))
        # Read a literal navigation target; never execute JavaScript.
        for target in re.findall(r"(?:location\.href|window\.location)\s*=\s*['\"]([^'\"]+)['\"]",a.get('onclick','')):
            self.links.add(urljoin(self.url,target))
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.ignore:self.ignore-=1
    def handle_data(self,text):
        if not self.ignore:self.text.append(text)

def publication_context(chain,root,target_url,registry=None):
    if not chain:return ''
    if not target_url:raise ValueError('Publication context requires a captured target URL')
    root=Path(root).resolve();parsed=[]
    for relative in chain:
        if not isinstance(relative,str) or Path(relative).is_absolute():raise ValueError('Context manifest must be relative')
        manifest=(root/relative).resolve();manifest.relative_to(root)
        m=json.loads(manifest.read_text(encoding='utf-8-sig'))
        file=(manifest.parent/m['file']).resolve();file.relative_to(root)
        data=file.read_bytes()
        if m.get('mode')!='network' or len(data)!=m['bytes'] or hashlib.sha256(data).hexdigest()!=m['sha256']:
            raise ValueError('Publication context capture/hash mismatch')
        host=urlparse(m['final_url']).hostname
        if host!=urlparse(target_url).hostname:raise ValueError('Publication context must have same official host as table')
        if registry is not None:
            owners=[a for a in registry.get('hosts',[]) if a.get('host')==host and a.get('verified') is True and a.get('publisher')==m.get('publisher') and a.get('evidence_url')]
            if not owners:raise ValueError('Publication context publisher is not registered')
        p=ContextHTML(m['final_url']);p.feed(data.decode(m.get('charset') or 'utf-8',errors='strict'))
        parsed.append((m,p))
    for i,(m,p) in enumerate(parsed):
        next_url=parsed[i+1][0]['final_url'] if i+1<len(parsed) else target_url
        if next_url not in p.links:raise ValueError('Publication context navigation link missing: '+next_url)
    return ' '.join(' '.join(p.text) for m,p in parsed)
