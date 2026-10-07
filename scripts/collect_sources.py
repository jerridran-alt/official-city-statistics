"""Bounded catalog traversal; captures one source for use by every research city."""
import argparse
import json
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
from official_fetch import fetch
from stats_core import save
from failure_types import classify


def collect(seed, registry, output, depth=1, limit=10, engine='http', network_state=None):
    hosts = {r['host'] for r in json.loads(Path(registry).read_text(encoding='utf-8-sig'))['hosts'] if r.get('verified') is True}
    queue, seen, results = deque([(seed, 0)]), set(), []
    while queue and len(results) < limit:
        url, level = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        try:
            args = SimpleNamespace(url=url, registry=registry, output=output, html=None, refresh=False, encoding=None, retries=0, timeout=25, max_bytes=100 * 1024 * 1024, engine=engine, wait_selector=None,network_state=network_state)
            # Attachments are retrieved over HTTP rather than rendered as browser pages.
            if urlparse(url).path.lower().endswith(('.pdf', '.xls', '.xlsx', '.zip')):
                args.engine = 'http'
            record = fetch(args)
            results.append({'url': url, 'depth': level, 'status': 'ok', 'sha256': record['sha256'], 'file': record['file'], 'mode': record['mode'], 'cache_hit': record.get('cache_hit', False)})
            if level < depth:
                for link in record['links']:
                    if (link['is_statistics_hint'] or link['is_attachment'] or link.get('is_catalog_frame')) and urlparse(link['url']).hostname in hosts:
                        queue.append((link['url'], level + 1))
        except Exception as exc:
            results.append({'url':url,'depth':level,'status':'failed','failure':classify(exc)})
    return {'sources': results, 'queued_not_visited': len(queue), 'limit_reached': bool(queue), 'note': 'Discovery is bounded and does not establish completeness of a website or research sample.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('url', 'registry', 'output'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--depth', type=int, choices=(0, 1, 2), default=1)
    p.add_argument('--limit', type=int, default=10)
    p.add_argument('--engine', choices=('http', 'browser'), default='http')
    p.add_argument('--network-state')
    a = p.parse_args()
    if not 1 <= a.limit <= 100:
        p.error('limit must be between 1 and 100')
    result = collect(a.url, a.registry, a.output, a.depth, a.limit, a.engine, a.network_state)
    save(Path(a.output) / 'collection_report.json', result)
    print(json.dumps({'sources': len(result['sources']), 'failed': sum(r['status'] == 'failed' for r in result['sources']), 'queued_not_visited': result['queued_not_visited']}))
    return 1 if any(r['status'] == 'failed' for r in result['sources']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
