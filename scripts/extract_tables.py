"""Parse once, capture every city row, and separately annotate research-sample matches."""
import argparse
import hashlib
import json
from pathlib import Path
from stats_core import PARSER_VERSION, cell_at, norm, number, read_source, save,table_health
from failure_types import classify


def extract(parsed, mapping, config, source_file, evidence_root, capture_manifest=None):
    units = config.get('units', [])
    aliases = {}
    for unit in units:
        for name in [unit['name']] + unit.get('aliases', []):
            key = norm(name)
            if key in aliases and aliases[key]['id'] != unit['id']:
                raise ValueError('Ambiguous city alias: ' + name)
            aliases[key] = unit
    root = Path(evidence_root).resolve()
    file = Path(source_file).resolve().relative_to(root).as_posix()
    capture = None if capture_manifest is None else Path(capture_manifest).resolve().relative_to(root).as_posix()
    capture_url = None if capture_manifest is None else json.loads(Path(capture_manifest).read_text(encoding='utf-8-sig'))['final_url']
    records, skipped, errors = [], [], []
    for spec in mapping['tables']:
        ti = spec['table_index']
        table = parsed['tables'][ti]
        health=table_health(table,spec)
        if health:
            errors.append({'table':ti,'code':'SUSPICIOUS_TABLE_STRUCTURE','reason':'结构可疑，需人工/视觉核对','details':health})
            continue
        for ri in range(spec['data_start_row'], len(table['cells'])):
            city_pos = [ri, spec['city_column']]
            city_text = cell_at(table, city_pos)
            ignored = spec.get('skip_row_labels', ['全省', '全国', '合计', '总计', '省合计', 'Total'])
            if not norm(city_text) or any(norm(city_text).startswith(norm(label)) for label in ignored):
                skipped.append({'table': ti, 'row': ri, 'city_text': city_text, 'reason': 'empty label or configured non-city aggregate'})
                continue
            unit = aliases.get(norm(city_text))
            source_row_id = hashlib.sha256(json.dumps([parsed['source_sha256'], ti, city_pos, city_text], ensure_ascii=False).encode()).hexdigest()[:24]
            research_id = unit['id'] if unit else None
            city_name = unit['name'] if unit else city_text
            for col in spec['columns']:
                if col['indicator'] not in config['keep_indicators'] or not config['years'][0] <= col['year'] <= config['years'][1]:
                    continue
                pos = [ri, col['column']]
                try:
                    raw = cell_at(table, pos)
                    value = number(raw)
                    if value is None:
                        empty=norm(raw) in ('','—','–','..','...','N/A','NA','未公布','不详')
                        item={'table':ti,'cell':pos,'raw':raw,'reason':'source missing-value marker' if empty else 'unsupported numeric cell; parsing requires review'}
                        (skipped if empty else errors).append(item)
                        continue
                    if pos in table.get('formulas', []):
                        raise ValueError('Formula cell requires explicit review; not extracted as a literal')
                    if pos in table.get('display_requires_review', []):
                        raise ValueError('Percentage/date/scaled display format requires review; raw storage must not be mislabeled as printed value')
                    headers = col['header_cells']
                    header_text = ' '.join(cell_at(table, h) for h in headers)
                    required = {'indicator': col.get('indicator_evidence', col['indicator']), 'year': str(col['year']), 'unit': col['unit']}
                    if any(norm(v) not in norm(header_text) for v in required.values()):
                        raise ValueError('Configured indicator/year/unit is not supported by the referenced header cells')
                    for quote in (spec['scope_quote'], mapping['class_quote'], mapping['edition_quote']):
                        if not quote or norm(quote) not in norm(parsed['text']):
                            raise ValueError('Missing original context quote: ' + str(quote))
                    identity = json.dumps([parsed['source_sha256'], ti, pos, research_id or source_row_id, col['indicator'], col['year'], spec['scope'], mapping['source_class'], mapping['edition'], capture_url], ensure_ascii=False)
                    record = {'id': hashlib.sha256(identity.encode()).hexdigest()[:24], 'research_id': research_id, 'source_row_id': source_row_id, 'identity_status': 'matched' if unit else 'unmapped', 'city': city_name, 'year': col['year'], 'indicator': col['indicator'], 'unit': col['unit'], 'value': value, 'source_class': mapping['source_class'], 'edition': mapping['edition'], 'geographic_scope': spec['scope'], 'is_derived': False, 'evidence': {'file': file, 'sha256': parsed['source_sha256'], 'format': parsed['format'], 'encoding': parsed['encoding'], 'table_index': ti, 'cell': pos, 'city_cell': city_pos, 'city_text': city_text, 'value_text': raw, 'header_cells': headers, 'indicator_quote': required['indicator'], 'scope_quote': spec['scope_quote'], 'class_quote': mapping['class_quote'], 'edition_quote': mapping['edition_quote'], 'capture_manifest': capture, 'capture_url': capture_url}}
                    records.append(record)
                except (KeyError, IndexError, ValueError) as exc:
                    errors.append({'table': ti, 'cell': pos, 'city': city_name, 'error': str(exc)})
    return {'records': records, 'skipped': skipped, 'errors': errors, 'source_cities_extracted': len({r['source_row_id'] for r in records}), 'research_units_matched': len({r['research_id'] for r in records if r['research_id'] is not None})}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--format', required=True, choices=('html', 'csv', 'xlsx', 'pdf'))
    p.add_argument('--config', required=True)
    p.add_argument('--mapping', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--cache-dir', required=True)
    p.add_argument('--evidence-root', required=True)
    p.add_argument('--capture-manifest')
    p.add_argument('--encoding', default='utf-8-sig')
    a = p.parse_args()
    try:
        return execute(a)
    except Exception as exc:
        problem=classify(exc)
        report={'status':'unparsed','records':0,'data_complete':False,'source':a.input,'failure':problem,'detected_tables':problem.get('detected_tables')}
        save(str(a.output)+'.report.json',report)
        print(json.dumps(report,ensure_ascii=False))
        return 1


def execute(a):
    if a.format=='pdf':
        import importlib.util
        if importlib.util.find_spec('pdfplumber') is None:raise ModuleNotFoundError('PDF backend pdfplumber unavailable; run bootstrap.py --profile basic')
    fingerprint = hashlib.sha256(Path(a.input).read_bytes()).hexdigest()
    cache_key = hashlib.sha256((fingerprint + a.format + a.encoding + PARSER_VERSION).encode()).hexdigest()
    cached = Path(a.cache_dir) / (cache_key + '.tables.json')
    checksum = cached.with_suffix('.sha256')
    reused = False
    if cached.exists() and checksum.exists() and hashlib.sha256(cached.read_bytes()).hexdigest() == checksum.read_text().strip():
        parsed = json.loads(cached.read_text(encoding='utf8'))
        reused = parsed.get('source_sha256') == fingerprint and parsed.get('parser_version') == PARSER_VERSION
    if not reused:
        parsed = read_source(a.input, a.format, a.encoding)
        save(cached, parsed)
        checksum.write_text(hashlib.sha256(cached.read_bytes()).hexdigest(), encoding='ascii')
    mapping = json.loads(Path(a.mapping).read_text(encoding='utf-8-sig'))
    config = json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
    result = extract(parsed, mapping, config, a.input, a.evidence_root, a.capture_manifest)
    failed=bool(result['errors']) or not result['records']
    status='empty_or_error' if failed else 'extracted_candidates'
    report={k:v for k,v in result.items() if k!='records'}|{'status':status,'data_complete':False,'detected_tables':len(parsed['tables']),'records':len(result['records']),'table_cache':str(cached),'source_table_cache_reused':reused}
    if result['records']:save(a.output,result['records'])
    else:report['reason']='识别到 0 条指标记录，来源未解析，非数据齐全；改走正文/OCR/视觉或更换源'
    save(str(a.output)+'.report.json',report)
    print(json.dumps({'status':status,'records':len(result['records']),'cities':result['source_cities_extracted'],'matched_research_cities':result['research_units_matched'],'errors':len(result['errors']),'detected_tables':len(parsed['tables']),'source_table_cache_reused':reused,'reason':report.get('reason')},ensure_ascii=False))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
