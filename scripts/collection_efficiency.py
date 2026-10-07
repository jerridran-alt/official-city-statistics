"""Rank tables before acquisition; preserve full-table extraction and province export gates."""
import argparse,json,hashlib
from pathlib import Path

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def key(r):return (r.get('code',r.get('research_id',r.get('city'))),r['year'],r['indicator'],r.get('geographic_scope','full_city'))
def plan_tables(tables,selected,reviewed_sources=()):
    present={key(r) for r in selected};done=set(reviewed_sources);out=[]
    for table in tables:
        # Table metadata only estimates yield, never proves actual values exist.
        expected={key(r) for r in table.get('expected_keys',[])};missing=expected-present
        item={**table,'expected_new_values':len(missing),'expected_keys_count':len(expected),'estimated_new_density':len(missing)/len(expected) if expected else None,'read_all_cities':True}
        if not expected:item['action']='inspect_unknown_coverage'
        elif missing:item['action']='acquire_or_reuse_table'
        elif table.get('source_sha256') in done and not table.get('newer_eligible_edition'):item['action']='reuse_reviewed_table'
        else:item['action']='version_or_scope_review'
        out.append(item)
    return sorted(out,key=lambda r:(r['expected_new_values'],bool(r.get('energy_priority')),r.get('edition',0)),reverse=True)

def export_ready(batch):
    pending=batch.get('pending_tables',[]);decision=batch.get('decision')
    if decision not in ('province_complete','province_first_pass_closed_with_gaps'):raise ValueError('Province batch not closed; keep collecting in JSON, defer Excel')
    if decision=='province_complete' and (pending or batch.get('remaining_gaps')):raise ValueError('Pending work cannot be called complete')
    if not batch.get('delta_verified') or not batch.get('old_keys_preserved') or not batch.get('panel_shape_verified'):raise ValueError('Delta, old-key protection and panel-shape checks required')
    identity=digest({k:batch.get(k) for k in ('province','selected_sha256','decision')})
    return {'export_key':identity,'ready':True,'complete':decision=='province_complete','pending_tables':pending}

def main():
    p=argparse.ArgumentParser();p.add_argument('--tables',required=True);p.add_argument('--selected',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    tables=json.loads(Path(a.tables).read_text(encoding='utf8'));selected=json.loads(Path(a.selected).read_text(encoding='utf8'));selected=selected.get('selected',[]) if isinstance(selected,dict) else selected
    Path(a.output).write_text(json.dumps(plan_tables(tables,selected),ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()
