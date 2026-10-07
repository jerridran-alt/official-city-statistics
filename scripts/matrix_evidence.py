"""Replay matrix page/word/schema interpretation; OCR glyph accuracy still needs review."""
import json,math
from urllib.parse import urlparse
from document_evidence import resolve
from ocr_matrix import extract_matrix,digest

def verify_matrix(record,config,root,registry,cache):
    errors=[];origin={'capture_matched':False,'authority':None}
    try:
        if type(record.get('value')) not in (int,float) or not math.isfinite(record['value']):raise ValueError('Invalid matrix value')
        e=record['evidence'];source=resolve(root,e['file']);layout=resolve(root,e['ocr_artifact']);plan=resolve(root,e['matrix_plan']);capture=resolve(root,e['capture_manifest'])
        key=('matrix_replay',str(source),str(layout),str(plan),str(capture))
        if key not in cache:
            hashes=[digest(p) for p in (source,layout,plan)]
            result=extract_matrix(source,layout,plan,config,root,capture,registry)
            cache[key]={'hashes':hashes,'result':result}
        state=cache[key]
        if [e['sha256'],e['ocr_sha256'],e['plan_sha256']]!=state['hashes']:raise ValueError('Matrix source/OCR/plan hash mismatch')
        result=state['result']
        if result['pending']:raise ValueError('Matrix page/cell interpretation has unresolved pending items; resolve before audit approval')
        original=next((r for r in result['records'] if r['id']==record.get('id')),None)
        if original is None:raise ValueError('Matrix interpretation cannot be reproduced')
        for field in ('research_id','source_row_id','identity_status','city','year','indicator','unit','value','source_class','edition','geographic_scope','is_derived','evidence'):
            if original[field]!=record.get(field):raise ValueError('Matrix replay mismatch: '+field)
        cap=json.loads(capture.read_text(encoding='utf-8-sig'))
        if cap.get('mode') in ('network','browser_network'):
            owner=next((a for a in registry['hosts'] if a.get('host')==urlparse(cap['final_url']).hostname and a.get('verified') is True and a.get('publisher')==cap['publisher'] and a.get('evidence_url')),None)
            if owner is None:raise ValueError('Matrix network source publisher not registered')
            origin={'capture_matched':True,'authority':owner,'url':cap['final_url']}
    except (KeyError,ValueError,TypeError,OSError,IndexError,StopIteration) as exc:errors.append(str(exc))
    return {'id':record.get('id'),'machine_checks_passed':not errors,'errors':errors,'origin':origin,'semantic_review_required':True,'glyph_accuracy_certified':False,'verification_type':'matrix_original_page_words_and_plan_replay','review_note':'矩阵/跨页回放不是字形真值认证；离线存档没有新增网络入库资格。','ignored_self_declarations':[k for k in ('official_verified','value_verified','scope_verified') if k in record]}
