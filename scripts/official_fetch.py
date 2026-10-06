"""Bounded official-source retrieval and offline catalog discovery (stdlib only)."""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse


def write_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def check_url(url, hosts):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
        raise ValueError('Only HTTP(S) URLs without credentials are accepted')
    host = (parsed.hostname or '').lower()
    if host not in hosts:
        raise ValueError('Host not verified in registry: ' + host)
    return hosts[host]


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        super().__init__()
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Catalog(HTMLParser):
    def __init__(self, url):
        super().__init__()
        self.url, self.current, self.links = url, None, []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.current = {'url': urljoin(self.url, dict(attrs).get('href', '')), 'text': ''}

    def handle_data(self, data):
        if self.current is not None:
            self.current['text'] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            a = self.current
            a['text'] = ' '.join(a['text'].split())
            if urlparse(a['url']).scheme in ('http', 'https'):
                self.links.append(a)
            self.current = None


def inspect_html(body, url, charset='utf-8'):
    parser = Catalog(url)
    parser.feed(body.decode(charset, errors='replace'))
    unique = {(a['url'], a['text']): a for a in parser.links}
    links = list(unique.values())
    for a in links:
        a['is_attachment'] = urlparse(a['url']).path.lower().endswith(('.pdf', '.xls', '.xlsx', '.zip', '.doc', '.docx'))
        a['is_statistics_hint'] = any(x in a['text'] for x in ('统计', '年鉴', '公报'))
    return links


def fetch(args):
    registry = json.loads(Path(args.registry).read_text(encoding='utf-8-sig'))
    hosts = {r['host'].lower(): r for r in registry['hosts'] if r.get('verified') is True and r.get('publisher') and r.get('evidence_url')}
    owner = check_url(args.url, hosts)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(args.url.encode()).hexdigest()[:24]
    manifest = output / (key + '.json')
    if manifest.exists() and not args.refresh and not args.html:
        record = json.loads(manifest.read_text(encoding='utf-8'))
        check_url(record['final_url'], hosts)
        data = (output / record['file']).read_bytes()
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Cached file hash mismatch; preserve evidence and refresh')
        return dict(record, cache_hit=True)
    if args.html:
        body = Path(args.html).read_bytes()
        if len(body) > args.max_bytes:
            raise ValueError('Offline input exceeds max-bytes')
        final_url, ctype, charset = args.url, 'text/html', args.encoding or 'utf-8'
        mode = 'offline_html'
    else:
        opener = urllib.request.build_opener(CheckedRedirect(hosts))
        for attempt in range(args.retries + 1):
            try:
                req = urllib.request.Request(args.url, headers={'User-Agent': 'OfficialStatisticsResearch/1.0'})
                with opener.open(req, timeout=args.timeout) as response:
                    final_url = response.url
                    check_url(final_url, hosts)
                    body = response.read(args.max_bytes + 1)
                    ctype = response.headers.get('Content-Type', '')
                    charset = args.encoding or response.headers.get_content_charset() or 'utf-8'
                if len(body) > args.max_bytes:
                    raise ValueError('Response exceeds max-bytes; increase limit deliberately')
                break
            except (urllib.error.URLError, TimeoutError):
                if attempt == args.retries:
                    raise
                time.sleep(1)
        mode = 'network'
    digest = hashlib.sha256(body).hexdigest()
    blob = output / (digest + '.bin')
    blob.write_bytes(body)
    links = inspect_html(body, final_url, charset) if 'html' in ctype.lower() else []
    record = {'url': args.url, 'final_url': final_url, 'publisher': owner['publisher'], 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'mode': mode, 'content_type': ctype, 'bytes': len(body), 'sha256': digest, 'file': blob.name, 'links': links, 'statistical_values_verified': False}
    # Offline inspections must not replace a previously retrieved network manifest.
    target = output / (key + '.offline.json') if args.html else manifest
    write_json(target, record)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('url', 'registry', 'output'):
        p.add_argument('--' + key, required=True)
    p.add_argument('--html', help='Parse an existing HTML file without network')
    p.add_argument('--encoding')
    p.add_argument('--refresh', action='store_true')
    p.add_argument('--timeout', type=float, default=25)
    p.add_argument('--retries', type=int, choices=(0, 1), default=1)
    p.add_argument('--max-bytes', type=int, default=100 * 1024 * 1024)
    args = p.parse_args()
    if args.timeout <= 0 or args.max_bytes <= 0:
        p.error('timeout and max-bytes must be positive')
    try:
        r = fetch(args)
        print(json.dumps({'status': 'ok', 'bytes': r['bytes'], 'links': len(r['links']), 'cache_hit': r.get('cache_hit', False), 'mode': r['mode']}, ensure_ascii=False))
    except Exception as exc:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(args.url.encode()).hexdigest()[:24]
        write_json(out / (key + '.failure.json'), {'url': args.url, 'time': datetime.now(timezone.utc).isoformat(), 'error': str(exc)})
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
