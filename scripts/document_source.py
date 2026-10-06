"""Read article bodies/metadata and OCR artifacts without assuming a regular table."""
import hashlib,re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin


class Article(HTMLParser):
    def __init__(self,base_url=''):
        super().__init__();self.base_url=base_url;self.metadata={};self.parts=[];self.all_parts=[];self.images=[];self.attachments=[];self.stack=[];self.active=0;self.ignored=0;self.headings=[];self.heading=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='meta' and a.get('name'):self.metadata[a['name'].lower()]=a.get('content','')
        selected=tag=='article' or a.get('id') in ('fontzoom','article-content') or any(c in a.get('class','') for c in ('TRS_Editor','TRS_UEDITOR','article-content'))
        if tag not in ('img','br','meta','link','input','hr','source','area','base','embed','wbr'):
            self.stack.append((tag,selected));self.active+=int(selected)
        if tag in ('script','style'):self.ignored+=1
        if re.fullmatch('h[1-6]',tag):self.heading={'tag':tag,'text':''}
        if self.active and tag=='img' and a.get('src'):self.images.append({'url':urljoin(self.base_url,a['src']),'alt':a.get('alt',''),'preceding_text':''.join(self.parts)[-400:]})
        if tag=='a' and a.get('href') and re.search(r'\.(pdf|xlsx?|docx?)(?:\?|$)',a['href'],re.I):self.attachments.append({'url':urljoin(self.base_url,a['href']),'preceding_text':''.join(self.parts)[-400:]})
        if self.active and tag=='br':self.parts.append('\n')
    def handle_data(self,text):
        if self.ignored:return
        self.all_parts.append(text)
        if self.active:self.parts.append(text)
        if self.heading is not None:self.heading['text']+=text
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.ignored=max(0,self.ignored-1)
        if self.heading is not None and tag==self.heading['tag']:
            self.headings.append(self.heading['text'].strip());self.heading=None
        if self.active and tag in ('p','li'):self.parts.append('\n')
        if self.stack and tag in [v[0] for v in self.stack]:
            while self.stack:
                t,selected=self.stack.pop();self.active-=int(selected)
                if t==tag:break


def read_article(file,base_url='',encoding='utf-8-sig'):
    file=Path(file);parser=Article(base_url);parser.feed(file.read_text(encoding=encoding))
    title=parser.metadata.get('articletitle') or next((t for t in parser.headings if '公报' in t or '年鉴' in t),'')
    published=parser.metadata.get('pubdate') or parser.metadata.get('publishdate','')
    text=''.join(parser.parts) if parser.parts else ''.join(parser.all_parts)
    return {'title':title,'published':published,'metadata':parser.metadata,'text':text,'whole_text':''.join(parser.all_parts),'main_region_detected':bool(parser.parts),'images':parser.images,'attachments':parser.attachments,'source_sha256':hashlib.sha256(file.read_bytes()).hexdigest()}


def infer_context(article,config):
    title=article['title'];matches=[]
    for u in config.get('units',[]):
        for name in [u['name']]+u.get('aliases',[]):
            if name and name in title:matches.append(u);break
    if len(matches)!=1:raise ValueError('Document city is ambiguous; supply/verify a document context instead of guessing')
    year=re.search(r'(20\d{2})年',title)
    edition=re.search(r'(20\d{2})',article['published'])
    if not year or not edition:raise ValueError('Observation/publication year not supported by title and date metadata')
    return {'city':matches[0]['name'],'research_id':matches[0]['id'],'year':int(year[1]),'edition':int(edition[1]),'source_class':'communique' if '公报' in title else 'yearbook' if '年鉴' in title else 'government_document','title':title,'publication_date':article['published'],'context_status':'inferred_requires_review'}
