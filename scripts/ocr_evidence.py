"""Replay OCR layout interpretation and retain the mandatory glyph-review boundary."""
import hashlib,json,math
from pathlib import Path
from urllib.parse import urlparse
from ocr_extract import extract_ocr
from document_evidence import resolve


def verify_ocr(record,config,root,registry,cache):
    errors=[];origin={'capture_matched':False,'authority':None}
    try:
        if type(record.get('value')) not in (int,float) or not math.isfinite(record['value']) or type(record.get('year')) is not int:raise ValueError('Candidate value/year has invalid type or magnitude')
        e=record['evidence'];source=resolve(root,e['file']);layout=resolve(root,e['ocr_artifact']);capture_path=resolve(root,e['capture_manifest'])
        parent=resolve(root,e['parent_capture']) if e.get('parent_capture') else None
        key=('ocr_replay',str(source),str(layout),str(capture_path),str(parent))
        if key not in cache:
            digest=hashlib.sha256(source.read_bytes()).hexdigest();artifact_hash=hashlib.sha256(layout.read_bytes()).hexdigest()
            cap=json.loads(capture_path.read_text(encoding='utf-8-sig'))
            if cap['sha256']!=digest or cap['bytes']!=source.stat().st_size or hashlib.sha256((capture_path.parent/cap['file']).read_bytes()).hexdigest()!=digest:raise ValueError('OCR source and network capture mismatch')
            if e['sha256']!=digest or e['ocr_sha256']!=artifact_hash:raise ValueError('OCR/image evidence hash mismatch')
            cache[key]=extract_ocr(source,layout,config,root,capture_path,registry,parent)
        result=cache[key]
        match=next((r for r in result['records'] if r['id']==record['id']),None)
        if match is None:raise ValueError('OCR word positions/interpretation are not reproducible')
        for field in ('research_id','city','year','indicator','unit','value','source_class','edition','geographic_scope','is_derived','evidence'):
            if record.get(field)!=match[field]:raise ValueError('OCR evidence replay mismatch: '+field)
        cap=json.loads(capture_path.read_text(encoding='utf-8-sig'))
        if cap.get('mode') in ('network','browser_network'):
            host=urlparse(cap['final_url']).hostname
            authority=next((a for a in registry['hosts'] if a.get('host')==host and a.get('verified') is True and a.get('publisher')==cap['publisher']),None)
            if authority is None:raise ValueError('OCR original source not in verified authority registry')
            origin={'capture_matched':True,'authority':authority,'url':cap['final_url']}
    except (KeyError,ValueError,TypeError,OSError,StopIteration) as exc:errors.append(str(exc))
    return {'id':record.get('id'),'machine_checks_passed':not errors,'errors':errors,'origin':origin,'semantic_review_required':True,'verification_type':'ocr_artifact_and_source_chain_consistency','glyph_accuracy_certified':False,'review_note':'必须查看原图；高 OCR 分数、同一后端复跑或一致性检查都不等于字形真值。','ignored_self_declarations':[k for k in ('official_verified','value_verified','scope_verified') if k in record]}
