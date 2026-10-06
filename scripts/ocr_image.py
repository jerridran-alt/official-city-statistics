"""Optional Tesseract OCR to evidence-preserving word coordinates; no automatic verification."""
import argparse
import csv
import hashlib
import io
import shutil
import subprocess
from pathlib import Path
from stats_core import save


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--language', default='chi_sim+eng')
    p.add_argument('--timeout', type=int, default=60)
    a = p.parse_args()
    binary = shutil.which('tesseract')
    if not binary:
        p.error('Tesseract executable not installed; no OCR performed')
    source = Path(a.input)
    run = subprocess.run([binary, str(source), 'stdout', '-l', a.language, 'tsv'], capture_output=True, text=True, encoding='utf8', timeout=a.timeout)
    if run.returncode:
        raise RuntimeError(run.stderr.strip())
    words = [r for r in csv.DictReader(io.StringIO(run.stdout), delimiter='\t') if r.get('text', '').strip()]
    save(a.output, {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'source_name': source.name, 'engine': 'tesseract', 'language': a.language, 'words': words, 'verification_status': 'needs_visual_review', 'note': 'OCR confidence is not source truth. Preserve the image and inspect table boundaries, row/column associations, signs, and digits before constructing an audited record.'})
    print('OCR words:', len(words), '; visual review required')


if __name__ == '__main__':
    main()
