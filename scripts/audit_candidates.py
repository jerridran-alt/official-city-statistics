"""Audit declared evidence and required fields; does not verify facts or select versions."""
import argparse
import json
import math
from pathlib import Path
from urllib.parse import urlparse


def audit(records, scope):
    if not isinstance(records, list):
        raise ValueError('records must be a JSON array')
    start, end = scope['years']
    keep = set(scope['keep_indicators'])
    results = []
    for index, r in enumerate(records):
        issues = []
        if not isinstance(r, dict):
            results.append({'index': index, 'issues': ['record must be an object']})
            continue
        for k in ('research_id', 'city', 'indicator', 'unit', 'publisher', 'locator', 'original_text', 'geographic_scope'):
            if not isinstance(r.get(k), str) or not r[k].strip():
                issues.append('missing/non-text: ' + k)
        for k in ('url', 'publication_url'):
            parsed = urlparse(r.get(k, '') if isinstance(r.get(k, ''), str) else '')
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                issues.append('invalid URL: ' + k)
        y = r.get('year')
        if type(y) is not int or not start <= y <= end:
            issues.append('year outside research period or not integer')
        edition = r.get('edition')
        if type(edition) is not int or edition < 1900 or (type(y) is int and edition < y):
            issues.append('invalid publication edition')
        value = r.get('value')
        if type(value) not in (int, float) or not math.isfinite(value):
            issues.append('value must be finite original number')
        if not isinstance(r.get('indicator'), str) or r['indicator'] not in keep:
            issues.append('indicator outside project scope')
        if r.get('source_class') not in ('yearbook', 'communique', 'government_document'):
            issues.append('invalid source_class')
        for k in ('official_verified', 'value_verified', 'scope_verified'):
            if r.get(k) is not True:
                issues.append('not verified: ' + k)
        if r.get('is_derived') is not False:
            issues.append('derived or unknown derivation status')
        results.append({'index': index, 'research_id': r.get('research_id'), 'year': y, 'indicator': r.get('indicator'), 'issues': issues})
    bad = sum(bool(r['issues']) for r in results)
    return {'records': len(records), 'passed': len(records) - bad, 'failed': bad, 'all_passed': bad == 0, 'note': 'Schema/declaration check only; source and statistical correctness still require original-document verification.', 'results': results}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('records', 'scope', 'output'):
        p.add_argument('--' + key, required=True)
    a = p.parse_args()
    result = audit(json.loads(Path(a.records).read_text(encoding='utf-8-sig')), json.loads(Path(a.scope).read_text(encoding='utf-8-sig')))
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('records', 'passed', 'failed', 'all_passed')}))
    return 0 if result['all_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
