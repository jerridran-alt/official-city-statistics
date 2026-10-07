"""Exact audit reuse: original bytes, candidate, mapping and reviewer decisions remain bound."""
import hashlib,json
from pathlib import Path
from collection_efficiency import digest

def identity(record,config,registry,review,parser_version):
    return digest({'record':record,'config':config,'registry':registry,'review':review,'parser_version':parser_version})
def lookup(directory,record,config,registry,review,parser_version,source_file):
    if not review or review.get('decision')!='approve':return None
    source_file=Path(source_file)
    sha=hashlib.sha256(source_file.read_bytes()).hexdigest()
    expected=record.get('evidence',{}).get('sha256') or record.get('evidence',{}).get('source_sha256')
    if sha!=expected:return None
    p=Path(directory)/(identity(record,config,registry,review,parser_version)+'.json')
    if not p.exists():return None
    data=json.loads(p.read_text(encoding='utf8'))
    if data.get('source_sha256')!=sha or not data.get('result',{}).get('machine_checks_passed'):return None
    # Cache is an optimization for previous checks, never a new capture or approval.
    return {**data['result'],'audit_cache_hit':True,'fresh_capture':False}
def store(directory,record,config,registry,review,parser_version,source_file,result):
    if not review or review.get('decision')!='approve' or not result.get('machine_checks_passed'):return False
    # Also bind the external semantic review to this evidence and mapping.
    e=record.get('evidence',{});sha=hashlib.sha256(Path(source_file).read_bytes()).hexdigest()
    if sha!=(e.get('sha256') or e.get('source_sha256')) or review.get('source_sha256')!=sha:return False
    if e.get('plan_sha256') and review.get('plan_sha256')!=e['plan_sha256']:return False
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);p=directory/(identity(record,config,registry,review,parser_version)+'.json')
    p.write_text(json.dumps({'source_sha256':sha,'result':result},ensure_ascii=False,indent=2),encoding='utf8');return True
