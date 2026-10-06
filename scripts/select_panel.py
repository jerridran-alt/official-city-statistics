"""Select evidence-backed, separately reviewed observations with configurable priorities."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from audit_candidates import audit
from stats_core import save


def priority(record, authority, rules):
    for index, rule in enumerate(rules):
        match = rule.get('match', {})
        context = {'publisher_id': authority.get('publisher_id'), 'authority_level': authority.get('level'), 'source_class': record['source_class']}
        if all(context.get(k) == v for k, v in match.items()):
            return len(rules) - index
    return 0


def select(records, config, report, reviews):
    checks = {r['id']: r for r in report['results']}
    decisions = {r['record_id']: r for r in reviews}
    if len(decisions) != len(reviews):
        raise ValueError('Duplicate review decisions require explicit resolution')
    groups, pending, excluded = defaultdict(list), [], []
    research_ids = {u['id'] for u in config.get('units', [])}
    for r in records:
        if r.get('research_id') not in research_ids:
            excluded.append({'id': r['id'], 'city': r['city'], 'reason': 'preserved in source cache; not mapped into this research sample'})
            continue
        scope_rules=config.get('allowed_geographic_scopes',{})
        allowed=scope_rules.get(r['indicator'],scope_rules.get('default'))
        if allowed is not None and r['geographic_scope'] not in allowed:
            excluded.append({'id':r['id'],'city':r['city'],'reason':'ineligible geographic/statistical scope; source priority does not override compatibility'});continue
        check = checks.get(r['id'])
        review = decisions.get(r['id'], {})
        if review.get('decision')=='reject' and review.get('source_sha256')==r['evidence']['sha256'] and review.get('reviewer') and review.get('reason'):
            excluded.append({'id':r['id'],'city':r['city'],'reason':'explicit documented rejection: '+review['reason']});continue
        if not check or not check['machine_checks_passed'] or not check['origin']['capture_matched'] or review.get('decision') != 'approve' or review.get('source_sha256') != r['evidence']['sha256'] or not review.get('reviewer') or not review.get('reason'):
            pending.append({'id': r['id'], 'reason': 'missing consistent original evidence, network capture, or separate documented semantic review'})
            continue
        rank = priority(r, check['origin']['authority'], config['source_priorities'])
        if rank == 0:
            pending.append({'id': r['id'], 'reason': 'source does not match priority config'})
            continue
        key = (r['research_id'], r['year'], r['indicator'], r['geographic_scope'])
        groups[key].append((rank, r['edition'], r))
    selected, conflicts = [], []
    for key, versions in groups.items():
        best = max((p, e) for p, e, r in versions)
        top = [r for p, e, r in versions if (p, e) == best]
        distinct = {(r['value'], r['unit']) for r in top}
        if len(distinct) > 1:
            conflicts.append({'key': key, 'ids': [r['id'] for r in top], 'reason': 'equal priority and edition, conflicting originals; requires official correction/publication-date review'})
        else:
            selected.append(top[0])
    return {'selected': selected, 'pending': pending, 'conflicts': conflicts, 'excluded_from_panel': excluded}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('records', 'config', 'evidence-root', 'registry', 'reviews', 'output'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--csv', help='Optional long-form original-data CSV; never overwrites sources')
    a = p.parse_args()
    records = json.loads(Path(a.records).read_text(encoding='utf-8-sig'))
    config = json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
    report = audit(records, config, a.evidence_root, json.loads(Path(a.registry).read_text(encoding='utf-8-sig')))
    result = select(records, config, report, json.loads(Path(a.reviews).read_text(encoding='utf-8-sig')))
    save(a.output, result)
    if a.csv and result['selected']:
        fields = ['research_id', 'city', 'year', 'indicator', 'geographic_scope', 'unit', 'value', 'source_class', 'edition', 'id']
        out = Path(a.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(result['selected'])
    print(json.dumps({k: len(v) for k, v in result.items()}))
    return 1 if not result['selected'] or result['pending'] or result['conflicts'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
