"""Independent replay of prose rules and source capture, separate from table extraction."""
import hashlib,json,math
from pathlib import Path
from urllib.parse import urlparse
from document_extract import extract_article


def resolve(root,relative):
    path=(Path(root)/relative).resolve();path.relative_to(Path(root).resolve());return path


def verify_article(record,config,root,registry,cache):
    errors=[];origin={'capture_matched':False,'authority':None}
    try:
        if type(record.get('value')) not in (int,float) or not math.isfinite(record['value']) or type(record.get('year')) is not int:raise ValueError('Candidate value/year has invalid type or magnitude')
        e=record['evidence'];file=resolve(root,e['file']);capture_path=resolve(root,e['capture_manifest']);capture=json.loads(capture_path.read_text(encoding='utf-8-sig'))
        key=('article_replay',str(file),str(capture_path))
        if key not in cache:
            digest=hashlib.sha256(file.read_bytes()).hexdigest()
            if digest!=capture['sha256'] or capture['bytes']!=file.stat().st_size or hashlib.sha256((capture_path.parent/capture['file']).read_bytes()).hexdigest()!=digest:raise ValueError('Capture and original article mismatch')
            cache[key]=extract_article(file,config,root,capture_path)
        result=cache[key]
        match=next((r for r in result['records'] if r['id']==record['id']),None)
        if match is None:raise ValueError('Candidate rule/span not reproducible from original article')
        for field in ('research_id','city','year','indicator','unit','value','source_class','edition','geographic_scope','is_derived'):
            if record.get(field)!=match[field]:raise ValueError('Original-article replay mismatch: '+field)
        if e!=match['evidence']:raise ValueError('Original article offsets/quote/provenance mismatch')
        if capture.get('mode') in ('network','browser_network'):
            host=urlparse(capture['final_url']).hostname
            authority=next((h for h in registry.get('hosts',[]) if h.get('host')==host and h.get('verified') is True and h.get('publisher')==capture['publisher']),None)
            if authority is None:raise ValueError('Article publisher/host not in verified authority registry')
            origin={'capture_matched':True,'authority':authority,'url':capture['final_url']}
    except (KeyError,ValueError,TypeError,OSError,StopIteration) as exc:errors.append(str(exc))
    return {'id':record.get('id'),'machine_checks_passed':not errors,'errors':errors,'origin':origin,'semantic_review_required':True,'verification_type':'original_article_rule_replay','ignored_self_declarations':[k for k in ('official_verified','value_verified','scope_verified') if k in record]}
