"""Sample PDF body pages, never classify a whole book from its cover."""
import argparse
import hashlib
import json
from pathlib import Path


def sample_pages(total, requested=None):
    if total < 1:
        raise ValueError('Empty PDF')
    pages = requested if requested is not None else sorted({1, min(3, total), min(8, total), max(1, total // 2), total})
    if not pages or len(pages) > 8 or any(not isinstance(p, int) or not 1 <= p <= total for p in pages):
        raise ValueError('Supply 1..8 valid original PDF page numbers')
    return sorted(set(pages))


def inspect_pages(total, read_text, requested=None):
    samples = []
    for page in sample_pages(total, requested):
        text = read_text(page)
        count = sum(c.isalnum() for c in text)
        samples.append({'page': page, 'text_characters': count, 'text_layer': count >= 30, 'text_preview': text[:1200]})
    layers = {p['text_layer'] for p in samples}
    kind = 'mixed_sample' if len(layers) > 1 else 'text_sample' if True in layers else 'scan_or_sparse_sample'
    return {'total_pages': total, 'sampled_pages': samples, 'classification': kind, 'data_complete': False,
            'next_action': 'inspect_toc_and_target_pages', 'note': 'Sampling does not establish table structure or whole-document reliability.'}


def probe(file, requested=None):
    import pypdfium2 as pdfium
    file = Path(file)
    doc = pdfium.PdfDocument(file)
    def read(page):
        obj = doc[page - 1]
        try:
            text = obj.get_textpage()
            try:
                return text.get_text_range()
            finally:
                text.close()
        finally:
            obj.close()
    try:
        result = inspect_pages(len(doc), read, requested)
    finally:
        doc.close()
    result['source_sha256'] = hashlib.sha256(file.read_bytes()).hexdigest()
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--pages', help='Optional 1..8 original page numbers, comma-separated')
    a = p.parse_args()
    try:
        result = probe(a.input, [int(n) for n in a.pages.split(',')] if a.pages else None)
        code = 0
    except Exception as exc:
        result = {'status': 'probe_failed', 'reason': str(exc), 'data_complete': False}
        code = 1
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'sampled_pages'}, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
