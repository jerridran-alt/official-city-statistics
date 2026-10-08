"""Embedded city-level URL lookup; municipalities reuse provincial work."""
import argparse,json
from pathlib import Path
from collection_efficiency import fallback_keys,key

def lookup(name,catalog=None):
    catalog=Path(catalog) if catalog else Path(__file__).resolve().parents[1]/'assets/city_yearbook_urls.json'
    data=json.loads(catalog.read_text(encoding='utf8'))
    found=next((e for e in data['entries'] if e['name']==name or e['code']==name or e.get('supplied_code')==name),None)
    return found or {'name':name,'action':'not_in_url_catalog','yearbook_url':None,'validation':'unknown'}

def plan_city(name,gaps,checks=(),catalog=None):
    entry=lookup(name,catalog)
    if entry['action'] in ('reuse_province_layer','not_in_url_catalog'):return entry
    needed={key(r) for r in gaps if str(r.get('code',r.get('research_id','')))==entry['code'] or r.get('city')==entry['name']}
    eligible=fallback_keys(needed,'city',checks)
    if not eligible:return {**entry,'action':'defer_until_provincial_gap_checked','eligible_gap_count':0}
    return {**entry,'action':'use_supplied_city_url' if entry['yearbook_url'] else 'missing_city_url_check_official_communique_or_verified_local_catalog','eligible_gap_count':len(eligible),'read_all_units_in_table':True}

def main():
    p=argparse.ArgumentParser();p.add_argument('--city',required=True);p.add_argument('--catalog');p.add_argument('--gaps');p.add_argument('--checks');a=p.parse_args()
    data=plan_city(a.city,json.loads(Path(a.gaps).read_text(encoding='utf8')),json.loads(Path(a.checks).read_text(encoding='utf8')) if a.checks else [],a.catalog) if a.gaps else lookup(a.city,a.catalog)
    print(json.dumps(data,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
