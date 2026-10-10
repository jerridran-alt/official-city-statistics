"""Rank tables before acquisition; preserve full-table extraction and province export gates."""
import argparse,json,hashlib
from pathlib import Path

def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def key(r):return (r.get('code',r.get('research_id',r.get('city'))),r['year'],r['indicator'],r.get('geographic_scope','full_city'))
def fallback_keys(missing,level,checks):
    """Unlock lower yearbooks only for documented city/year/indicator/scope gaps."""
    if level not in ('province','city'):return set()
    ancestors={'city':['province']}.get(level,[])
    documented={(key(c),c.get('level')) for c in checks if c.get('status') in ('missing','unavailable','scope_mismatch') and c.get('reason') and c.get('source_refs')}
    return {k for k in missing if all((k,a) in documented for a in ancestors)}

def plan_tables(tables,selected,reviewed_sources=(),fallback_checks=()):
    present={key(r) for r in selected};done=set(reviewed_sources);out=[]
    for table in tables:
        # Table metadata only estimates yield, never proves actual values exist.
        expected={key(r) for r in table.get('expected_keys',[])};missing=expected-present
        item={**table,'expected_new_values':len(missing),'expected_keys_count':len(expected),'estimated_new_density':len(missing)/len(expected) if expected else None,'read_all_cities':True}
        cost=table.get('estimated_seconds')
        if cost is not None and (type(cost) not in (int,float) or cost<=0):raise ValueError('estimated_seconds must be a positive measured/planned table cost')
        item['expected_new_values_per_second']=len(missing)/cost if cost else None
        item['version_review_due']=bool(table.get('newer_eligible_edition') or table.get('scope_changed') or table.get('same_source_correction_due'))
        if not expected:item['action']='inspect_unknown_coverage'
        elif missing:item['action']='acquire_or_reuse_table'
        elif table.get('source_sha256') in done and not item['version_review_due']:item['action']='reuse_reviewed_table'
        else:item['action']='version_or_scope_review'
        level=table.get('yearbook_level') or (table.get('authority_level') if table.get('source_class')=='yearbook' else None)
        item['collection_level']=level or 'unknown'
        if level in ('county','district','national'):
            item['action']='exclude_outside_province_city_collection_levels'
        elif level=='city':
            unlocked=fallback_keys(missing,level,fallback_checks)
            item['unlocked_gap_keys']=[list(k) for k in sorted(unlocked)]
            item['unlocked_gap_count']=len(unlocked)
            item['deferred_gap_count']=len(missing-unlocked)
            if not unlocked:
                item['action']='defer_lower_yearbook_until_documented_upper_gaps'
        elif level is None:
            item['publication_level_requires_review']=True
            if expected and item['action']!='reuse_reviewed_table':item['action']='inspect_publication_level_metadata_only'
        out.append(item)
    levels={'province':1,'city':2,'unknown':0}
    return sorted(out,key=lambda r:(r['action'].startswith(('defer_','exclude_')),levels.get(r['collection_level'],9),-int(r['version_review_due']),-(r['expected_new_values_per_second'] or 0),-r['expected_new_values'],-(r['estimated_new_density'] or 0),-int(bool(r.get('energy_priority'))),-r.get('edition',0)))

def export_ready(batch):
    pending=batch.get('pending_tables',[]);decision=batch.get('decision')
    if decision not in ('province_complete','province_first_pass_closed_with_gaps'):raise ValueError('Province batch not closed; keep collecting in JSON, defer Excel')
    if decision=='province_complete' and (pending or batch.get('remaining_gaps')):raise ValueError('Pending work cannot be called complete')
    if not batch.get('delta_verified') or not batch.get('old_keys_preserved') or not batch.get('panel_shape_verified'):raise ValueError('Delta, old-key protection and panel-shape checks required')
    identity=digest({k:batch.get(k) for k in ('province','selected_sha256','decision')})
    return {'export_key':identity,'ready':True,'complete':decision=='province_complete','pending_tables':pending}

def main():
    p=argparse.ArgumentParser();p.add_argument('--tables',required=True);p.add_argument('--selected',required=True);p.add_argument('--output',required=True);p.add_argument('--fallback-checks',help='Documented upper-level gaps, not a bare completion flag');a=p.parse_args()
    tables=json.loads(Path(a.tables).read_text(encoding='utf8'));selected=json.loads(Path(a.selected).read_text(encoding='utf8'));selected=selected.get('selected',[]) if isinstance(selected,dict) else selected
    checks=json.loads(Path(a.fallback_checks).read_text(encoding='utf8')) if a.fallback_checks else []
    Path(a.output).write_text(json.dumps(plan_tables(tables,selected,fallback_checks=checks),ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()
