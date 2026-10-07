"""Bounded official-source retrieval and offline catalog discovery (stdlib only)."""
import argparse
import asyncio
import hashlib
import json
import re
import codecs
from html import unescape
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
        attrs = dict(attrs)
        if tag in ('frame', 'iframe') and attrs.get('src'):
            self.links.append({'url': urljoin(self.url, attrs['src'].replace('\\', '/')), 'text': attrs.get('title') or attrs.get('name') or 'frame', 'discovery': 'frame_src', 'is_catalog_frame': bool(re.search(r'left|contents|mulu|menu|index', attrs.get('src','')+' '+attrs.get('name',''), re.I))})
        if tag == 'a':
            href = attrs.get('href', '')
            if not href or href.lower().startswith('javascript:'):
                literal = re.search(r'(?:window\.)?open\s*\(\s*([\x27\"])(.*?)\1', attrs.get('onclick',''), re.I)
                href = literal.group(2) if literal else ''
            self.current = {'url': urljoin(self.url, href.replace('\\', '/')), 'text': '', 'title': attrs.get('title','')}

    def handle_data(self, data):
        if self.current is not None:
            self.current['text'] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            a = self.current
            a['text'] = ' '.join(a['text'].split()) or a.pop('title','')
            if urlparse(a['url']).scheme in ('http', 'https'):
                self.links.append(a)
            self.current = None


def inspect_html(body, url, charset='utf-8'):
    parser = Catalog(url)
    text=body.decode(charset, errors='replace')
    parser.feed(text)
    # JPage-style official catalogs store literal link HTML inside CDATA.
    # Read those literal fragments; do not execute JavaScript or construct URLs.
    for match in re.finditer(r'<!\[CDATA\[(.*?)\]\]>', text, re.S):
        fragment=Catalog(url);fragment.feed(match.group(1))
        for link in fragment.links:
            link.update(discovery='embedded_cdata',source_fragment_span=[match.start(1),match.end(1)])
            parser.links.append(link)
    unique = {(a['url'], a['text']): a for a in parser.links}
    links = list(unique.values())
    for a in links:
        a['is_attachment'] = urlparse(a['url']).path.lower().endswith(('.pdf', '.xls', '.xlsx', '.zip', '.doc', '.docx'))
        a['is_statistics_hint'] = any(x in a['text'] for x in ('统计', '年鉴', '公报'))
    return links


def html_encoding(body, header=None, explicit=None):
    if explicit:return explicit
    if body.startswith(b'\xef\xbb\xbf'):return 'utf-8-sig'
    match=re.search(rb'charset\s*=\s*[\x27\"]?\s*([a-zA-Z0-9_-]+)',body[:8192],re.I)
    enc=header or (match.group(1).decode('ascii') if match else 'utf-8')
    codecs.lookup(enc)
    return 'gb18030' if enc.lower() in ('gb2312','gbk') else enc


def document_title(body, encoding):
    match=re.search(r'<title\b[^>]*>(.*?)</title>',body.decode(encoding,errors='replace'),re.I|re.S)
    return unescape(re.sub(r'<[^>]+>','',match.group(1))).strip() if match else ''


async def browser_html(url, hosts, timeout, selector):
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError('Browser backend requires playwright and its Chromium runtime; HTTP mode has no extra dependency') from exc
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            async def guard(route):
                request = route.request
                if request.is_navigation_request():
                    try:
                        check_url(request.url, hosts)
                    except ValueError:
                        await route.abort()
                        return
                await route.continue_()
            await page.route('**/*', guard)
            response = await page.goto(url, wait_until='domcontentloaded', timeout=int(timeout * 1000))
            if response is None or response.status >= 400:
                raise ValueError('Browser navigation did not return a successful response')
            if selector:
                await page.wait_for_selector(selector, timeout=int(timeout * 1000))
            check_url(page.url, hosts)
            return (await page.content()).encode('utf8'), page.url
        finally:
            await browser.close()


def _fetch(args):
    registry = json.loads(Path(args.registry).read_text(encoding='utf-8-sig'))
    hosts = {r['host'].lower(): r for r in registry['hosts'] if r.get('verified') is True and r.get('publisher') and r.get('evidence_url')}
    owner = check_url(args.url, hosts)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    engine = getattr(args, 'engine', 'http')
    key = hashlib.sha256((args.url + '\0' + engine).encode()).hexdigest()[:24]
    manifest = output / (key + '.json')
    if manifest.exists() and not args.refresh and not args.html:
        record = json.loads(manifest.read_text(encoding='utf-8'))
        check_url(record['final_url'], hosts)
        data = (output / record['file']).read_bytes()
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            raise ValueError('Cached file hash mismatch; preserve evidence and refresh')
        if 'html' in record.get('content_type','').lower() and record.get('catalog_parser_version')!='2.1':
            enc=html_encoding(data,explicit=record.get('encoding'))
            record.update(encoding=enc,links=inspect_html(data,record['final_url'],enc),document_title=document_title(data,enc),catalog_parser_version='2.1',links_reparsed_from_original=True)
            write_json(manifest,record)
        return dict(record, cache_hit=True)
    if args.html:
        body = Path(args.html).read_bytes()
        if len(body) > args.max_bytes:
            raise ValueError('Offline input exceeds max-bytes')
        final_url, ctype, charset = args.url, 'text/html', html_encoding(body,explicit=args.encoding)
        mode = 'offline_html'
    elif engine == 'browser':
        body, final_url = asyncio.run(browser_html(args.url, hosts, args.timeout, getattr(args, 'wait_selector', None)))
        if len(body) > args.max_bytes:
            raise ValueError('Rendered HTML exceeds max-bytes')
        ctype, charset, mode = 'text/html; charset=utf-8', 'utf-8', 'browser_network'
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
                    charset = html_encoding(body,response.headers.get_content_charset(),args.encoding) if 'html' in ctype.lower() else args.encoding or 'utf-8'
                if len(body) > args.max_bytes:
                    raise ValueError('Response exceeds max-bytes; increase limit deliberately')
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                from network_health import failure
                if not failure(exc)['retryable']:raise
                if attempt == args.retries:
                    raise
                time.sleep(1)
        mode = 'network'
    digest = hashlib.sha256(body).hexdigest()
    blob = output / (digest + '.bin')
    blob.write_bytes(body)
    links = inspect_html(body, final_url, charset) if 'html' in ctype.lower() else []
    owner = check_url(final_url, hosts)
    record = {'url': args.url, 'final_url': final_url, 'publisher': owner['publisher'], 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'mode': mode, 'engine': engine, 'rendered_dom': engine == 'browser', 'content_type': ctype, 'encoding': charset, 'bytes': len(body), 'sha256': digest, 'file': blob.name, 'links': links, 'statistical_values_verified': False}
    record['catalog_parser_version']='2.1'
    if 'html' in ctype.lower():record['document_title']=document_title(body,charset)
    # Offline inspections must not replace a previously retrieved network manifest.
    target = output / (key + '.offline.json') if args.html else manifest
    write_json(target, record)
    return record



def fetch(args):
    # Successful exact-byte cache is usable even while the host is cooling down.
    engine=getattr(args,'engine','http');output=Path(args.output)
    key=hashlib.sha256((args.url+'\0'+engine).encode()).hexdigest()[:24]
    if args.html or ((output/(key+'.json')).exists() and not args.refresh):return _fetch(args)
    from network_health import host_slot,finish,failure
    from types import SimpleNamespace
    parsed=urlparse(args.url);host=parsed.hostname
    origin=f'{parsed.scheme}://{host}:{parsed.port or (443 if parsed.scheme=="https" else 80)}'
    # Validate registry before touching host state or the network.
    registry=json.loads(Path(args.registry).read_text(encoding='utf-8-sig'))
    hosts={r['host'].lower():r for r in registry['hosts'] if r.get('verified') is True and r.get('publisher') and r.get('evidence_url')};check_url(args.url,hosts)
    directory=getattr(args,'network_state',None) or output/'.network_health'
    with host_slot(directory,origin,wait=min(30,args.timeout+2)) as (state,statefile):
        try:
            local=SimpleNamespace(**vars(args));local.retries=0
            result=_fetch(local)
        except Exception as exc:
            finish(state,statefile,exc)
            output.mkdir(parents=True,exist_ok=True)
            write_json(output/(key+'.failure.json'),{'url':args.url,'failure':failure(exc),'error':str(exc),'network_route':'existing configured route; unchanged','outbound_region':'unknown'})
            raise
        finish(state,statefile);return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('url', 'registry', 'output'):
        p.add_argument('--' + key, required=True)
    p.add_argument('--html', help='Parse an existing HTML file without network')
    p.add_argument('--encoding')
    p.add_argument('--engine', choices=('http', 'browser'), default='http')
    p.add_argument('--wait-selector', help='Browser mode: wait for a specific table/content selector')
    p.add_argument('--refresh', action='store_true')
    p.add_argument('--network-state', help='Shared host health directory for all batches in a project')
    p.add_argument('--timeout', type=float, default=25)
    p.add_argument('--retries', type=int, choices=(0, 1), default=0)
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
