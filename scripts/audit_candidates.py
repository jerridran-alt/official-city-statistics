"""Re-read original evidence; caller-supplied verification booleans confer no trust."""
import argparse
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from stats_core import cell_at, norm, number, read_source, save


def inside(root, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError('Evidence paths must be relative to evidence-root')
    path = (Path(root) / relative).resolve()
    path.relative_to(Path(root).resolve())
    return path


def verify(record, config, root, registry, parsed_cache):
    errors, origin = [], {'capture_matched': False, 'authority': None}
    try:
        if not isinstance(record, dict):
            raise ValueError('Record must be an object')
        r = record
        if type(r.get('year')) is not int or not config['years'][0] <= r['year'] <= config['years'][1]:
            raise ValueError('Observation year outside configured period')
        if r.get('indicator') not in config['keep_indicators']:
            raise ValueError('Indicator outside configured scope')
        if type(r.get('value')) not in (int, float) or not math.isfinite(r['value']):
            raise ValueError('Value must be a finite number')
        if r.get('is_derived') is not False:
            raise ValueError('Derived or unspecified derivation status')
        unit = next((u for u in config.get('units', []) if u['id'] == r.get('research_id')), None)
        if r.get('research_id') is not None and (unit is None or unit['name'] != r.get('city')):
            raise ValueError('Declared research identity not in project config')
        e = r.get('evidence')
        if not isinstance(e, dict):
            raise ValueError('Original-file evidence required; verification flags are insufficient')
        file = inside(root, e['file'])
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest != e['sha256']:
            raise ValueError('Original-file hash mismatch')
        key = (str(file), digest, e['format'], e.get('encoding', 'utf-8-sig'))
        if key not in parsed_cache:
            parsed_cache[key] = read_source(file, e['format'], key[3])
        parsed = parsed_cache[key]
        table = parsed['tables'][e['table_index']]
        raw = cell_at(table, e['cell'])
        if raw != e['value_text'] or number(raw) is None or Decimal(str(number(raw))) != Decimal(str(r['value'])):
            raise ValueError('Candidate does not match original numeric cell')
        if e['cell'] in table.get('formulas', []):
            raise ValueError('Formula cell is not a literal original value')
        if e['cell'] in table.get('display_requires_review', []):
            raise ValueError('Raw XLSX storage differs from a special formatted display; review required')
        city = cell_at(table, e['city_cell'])
        aliases = [unit['name']] + unit.get('aliases', []) if unit else [r['city']]
        if city != e['city_text'] or norm(city) not in {norm(v) for v in aliases}:
            raise ValueError('Original city row does not match recorded city identity')
        if e['city_cell'][0] != e['cell'][0]:
            raise ValueError('City and numeric cells are on different rows')
        headers = ' '.join(cell_at(table, p) for p in e['header_cells'])
        allowed = [r['indicator']] + config.get('indicator_aliases', {}).get(r['indicator'], [])
        if e['indicator_quote'] not in allowed:
            raise ValueError('Indicator alias not explicitly configured')
        for token in (e['indicator_quote'], str(r['year']), r['unit']):
            if not token or norm(token) not in norm(headers):
                raise ValueError('Indicator/year/unit unsupported by original referenced headers')
        for field in ('scope_quote', 'class_quote', 'edition_quote'):
            if not e.get(field) or norm(e[field]) not in norm(parsed['text']):
                raise ValueError('Context quotation absent from original: ' + field)
        if not r.get('geographic_scope') or norm(r['geographic_scope']) not in norm(e['scope_quote']):
            raise ValueError('Scope unsupported by context quotation')
        if type(r.get('edition')) is not int or r['edition'] < r['year'] or str(r['edition']) not in e['edition_quote']:
            raise ValueError('Edition unsupported by publication quotation')
        if r.get('source_class') not in ('yearbook', 'communique', 'government_document'):
            raise ValueError('Unknown publication class')
        if r['source_class'] == 'yearbook' and not any(x in e['class_quote'] for x in ('年鉴', 'Yearbook')):
            raise ValueError('Yearbook classification lacks a supporting title')
        if r['source_class'] == 'communique' and not any(x in e['class_quote'] for x in ('公报', 'Communiqué', 'Communique')):
            raise ValueError('Communiqué classification lacks a supporting title')
        source_row_id = hashlib.sha256(json.dumps([digest, e['table_index'], e['city_cell'], city], ensure_ascii=False).encode()).hexdigest()[:24]
        if r.get('source_row_id') != source_row_id:
            raise ValueError('Source-row identity is inconsistent')
        identity = json.dumps([digest, e['table_index'], e['cell'], unit['id'] if unit else source_row_id, r['indicator'], r['year'], r['geographic_scope'], r['source_class'], r['edition'], e.get('capture_url')], ensure_ascii=False)
        if r.get('id') != hashlib.sha256(identity.encode()).hexdigest()[:24]:
            raise ValueError('Record identity does not match original evidence location')
        if e.get('capture_manifest'):
            capture = json.loads(inside(root, e['capture_manifest']).read_text(encoding='utf-8-sig'))
            if e.get('capture_url') != capture.get('final_url'):
                raise ValueError('Captured URL does not match candidate provenance')
            capture_file = inside(root, e['capture_manifest']).parent / capture['file']
            if capture['sha256'] != digest or capture['bytes'] != file.stat().st_size or hashlib.sha256(capture_file.read_bytes()).hexdigest() != digest:
                raise ValueError('Capture manifest and original file are inconsistent')
            if capture.get('mode') in ('network', 'browser_network'):
                host = urlparse(capture['final_url']).hostname
                authorities = [a for a in registry.get('hosts', []) if a.get('host') == host and a.get('verified') is True and a.get('publisher') and a.get('evidence_url')]
                if not authorities:
                    raise ValueError('Capture host absent from externally configured authority registry')
                authority = authorities[0]
                if capture['publisher'] != authority['publisher']:
                    raise ValueError('Captured publisher inconsistent with authority registry')
                origin = {'capture_matched': True, 'authority': authority, 'url': capture['final_url']}
    except (KeyError, IndexError, ValueError, TypeError, OSError, StopIteration) as exc:
        errors.append(str(exc))
    return {'id': record.get('id') if isinstance(record, dict) else None, 'machine_checks_passed': not errors, 'errors': errors, 'origin': origin, 'semantic_review_required': True, 'ignored_self_declarations': [k for k in ('official_verified', 'value_verified', 'scope_verified') if isinstance(record, dict) and k in record]}


def audit(records, config, evidence_root, registry):
    cache = {}
    results = [verify(r, config, evidence_root, registry, cache) for r in records]
    ids = [r['id'] for r in results]
    for result in results:
        if result['id'] is not None and ids.count(result['id']) > 1:
            result['errors'].append('Duplicate record identity in batch')
            result['machine_checks_passed'] = False
    failed = sum(not r['machine_checks_passed'] for r in results)
    return {'records': len(records), 'passed': len(records) - failed, 'failed': failed, 'machine_checks_passed': failed == 0, 'source_files_read': len(cache), 'results': results, 'note': 'Original-cell/context consistency checks, not a certification of publisher identity or statistical meaning. Authority registry and semantic review remain explicit external evidence.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('records', 'config', 'evidence-root', 'registry', 'output'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    report = audit(json.loads(Path(a.records).read_text(encoding='utf-8-sig')), json.loads(Path(a.config).read_text(encoding='utf-8-sig')), a.evidence_root, json.loads(Path(a.registry).read_text(encoding='utf-8-sig')))
    save(a.output, report)
    print(json.dumps({k: report[k] for k in ('records', 'passed', 'failed', 'machine_checks_passed', 'source_files_read')}))
    return 0 if report['machine_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
