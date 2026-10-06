"""Original table readers and literal numeric parsing; no estimates or unit conversion."""
import csv
import hashlib
import io
import json
import re
import zipfile
import posixpath
import xml.etree.ElementTree as ET
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
from failure_types import SourceFailure

PARSER_VERSION = '3.0'


def number(text):
    text = str(text).strip().replace('\u2212', '-')
    negative_word = text.startswith(('下降', '减少'))
    if negative_word:
        text = text[2:]
    text = re.sub(r'[%‰]$', '', text.strip())
    if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', text):
        return None
    value = Decimal(text.replace(',', ''))
    if negative_word:
        if value < 0:
            return None
        value = -value
    return int(value) if value == value.to_integral_value() else float(value)


def expand(rows):
    occupied, origins = {}, {}
    for r, row in enumerate(rows):
        c = 0
        for cell in row:
            while (r, c) in occupied:
                c += 1
            rs, cs = cell['rowspan'], cell['colspan']
            if not 1 <= rs <= 100 or not 1 <= cs <= 100:
                raise ValueError('Unsupported span size')
            for rr in range(r, r + rs):
                for cc in range(c, c + cs):
                    if (rr, cc) in occupied:
                        raise ValueError('Overlapping merged cells')
                    occupied[rr, cc] = cell['text'].strip()
                    origins[rr, cc] = [r, c]
            c += cs
    if not occupied:
        return [], []
    nr = max(r for r, c in occupied) + 1
    nc = max(c for r, c in occupied) + 1
    return ([[occupied.get((r, c), '') for c in range(nc)] for r in range(nr)],
            [[origins.get((r, c), [r, c]) for c in range(nc)] for r in range(nr)])


class HTMLTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.text, self.rows = [], [], None
        self.row, self.cell, self.caption = None, None, ''
        self.in_caption, self.ignore = False, 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.ignore += 1
        if self.ignore:
            return
        a = dict(attrs)
        if tag == 'table':
            if self.rows is not None:
                raise ValueError('Nested tables require an explicit backend')
            self.rows, self.caption = [], ''
        elif tag == 'tr' and self.rows is not None:
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = {'text': '', 'rowspan': int(a.get('rowspan', 1)), 'colspan': int(a.get('colspan', 1))}
        elif tag == 'caption' and self.rows is not None:
            self.in_caption = True
        elif tag == 'br' and self.cell is not None:
            self.cell['text'] += ' '

    def handle_data(self, text):
        if self.ignore:
            return
        self.text.append(text)
        if self.cell is not None:
            self.cell['text'] += text
        if self.in_caption:
            self.caption += text

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.ignore:
            self.ignore -= 1
            return
        if self.ignore:
            return
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(self.cell)
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == 'caption':
            self.in_caption = False
        elif tag == 'table' and self.rows is not None:
            cells, origins = expand(self.rows)
            self.tables.append({'label': self.caption.strip(), 'cells': cells, 'origins': origins})
            self.rows = None


def xlsx_tables(path):
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    relns = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
    out = []
    with zipfile.ZipFile(path) as z:
        if sum(a.file_size for a in z.infolist()) > 100 * 1024 * 1024:
            raise ValueError('Expanded XLSX exceeds 100 MiB')
        strings = []
        formats, style_ids = {}, [0]
        if 'xl/styles.xml' in z.namelist():
            styles = ET.fromstring(z.read('xl/styles.xml'))
            formats = {int(v.get('numFmtId')): v.get('formatCode', '') for v in styles.findall('m:numFmts/m:numFmt', ns)}
            style_ids = [int(v.get('numFmtId', 0)) for v in styles.findall('m:cellXfs/m:xf', ns)] or [0]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(x.itertext()) for x in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', ns)]
        rels = {v.get('Id'): v.get('Target') for v in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        book = ET.fromstring(z.read('xl/workbook.xml'))
        for sheet in book.findall('m:sheets/m:sheet', ns):
            target = rels[sheet.get(relns)]
            name = posixpath.normpath('xl/' + target) if not target.startswith('/') else target.lstrip('/')
            if not name.startswith('xl/'):
                raise ValueError('Unsupported XLSX relationship')
            xml = ET.fromstring(z.read(name))
            values, formulas, display_review = {}, [], []
            for cell in xml.findall('.//m:sheetData/m:row/m:c', ns):
                address = cell.get('r', '')
                match = re.fullmatch(r'([A-Z]+)(\d+)', address)
                if not match:
                    raise ValueError('Missing XLSX cell address')
                c = 0
                for letter in match[1]:
                    c = c * 26 + ord(letter) - 64
                r, c = int(match[2]) - 1, c - 1
                if r >= 10000 or c >= 512:
                    raise ValueError('Sheet exceeds supported dimensions')
                if cell.find('m:f', ns) is not None:
                    formulas.append([r, c])
                style = int(cell.get('s', 0))
                fmt_id = style_ids[style] if style < len(style_ids) else 0
                fmt = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', '', formats.get(fmt_id, ''))
                if fmt_id in (9, 10) or 14 <= fmt_id <= 22 or 45 <= fmt_id <= 47 or '%' in fmt or re.search(r'[0#],+(?:[^0#]|$)', fmt):
                    display_review.append([r, c])
                v = cell.find('m:v', ns)
                text = '' if v is None else v.text or ''
                if cell.get('t') == 's':
                    text = strings[int(text)]
                elif cell.get('t') == 'inlineStr':
                    text = ''.join(cell.find('m:is', ns).itertext())
                elif cell.get('t') == 'b':
                    text = 'TRUE' if text == '1' else 'FALSE'
                values[r, c] = text
            if not values:
                continue
            nr = max(r for r, c in values) + 1
            nc = max(c for r, c in values) + 1
            cells = [[values.get((r, c), '') for c in range(nc)] for r in range(nr)]
            out.append({'label': sheet.get('name'), 'cells': cells, 'formulas': formulas, 'display_requires_review': display_review})
    return out


def read_source(path, fmt, encoding='utf-8-sig'):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if fmt == 'html':
        parser = HTMLTables()
        parser.feed(path.read_text(encoding=encoding))
        tables, text = parser.tables, ' '.join(parser.text)
    elif fmt == 'csv':
        text = path.read_text(encoding=encoding)
        try:
            dialect = csv.Sniffer().sniff(text[:8192])
        except csv.Error:
            dialect = csv.excel
        tables = [{'label': path.name, 'cells': list(csv.reader(io.StringIO(text), dialect))}]
    elif fmt == 'xlsx':
        tables = xlsx_tables(path)
        text = '\n'.join(t['label'] + '\n' + '\n'.join('\t'.join(r) for r in t['cells']) for t in tables)
    elif fmt == 'pdf':
        try:
            import pdfplumber
        except ImportError as exc:
            raise RuntimeError('PDF tables require pdfplumber; HTML/CSV/XLSX do not') from exc
        tables, pages = [], []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or '')
                for i, cells in enumerate(page.extract_tables()):
                    tables.append({'label': f'page {page.page_number} table {i}', 'page': page.page_number, 'cells': [[str(v or '') for v in row] for row in cells]})
        text = '\n'.join(pages)
    else:
        raise ValueError('Supported formats: html, csv, xlsx, pdf')
    if not tables:
        raise SourceFailure('NO_STRUCTURED_TABLES','识别到 0 张表，非数据齐全。未识别到结构化表格，请改走 OCR/视觉后端，或换 HTML/XLSX 源。',detected_tables=0)
    return {'parser_version': PARSER_VERSION, 'source_sha256': digest, 'format': fmt, 'encoding': encoding, 'text': text, 'tables': tables,'detected_tables':len(tables)}


def table_health(table,spec):
    cells=table.get('cells',[]);issues=[]
    start=spec.get('data_start_row',0)
    if not cells or start>=len(cells):
        return [{'code':'NO_DATA_ROWS','reason':'识别到 0 个数据行，来源未解析，非数据齐全'}]
    widths={len(row) for row in cells}
    if len(widths)>1:issues.append({'code':'INCONSISTENT_COLUMNS','reason':'结构可疑：行列数不一致，需人工/视觉核对'})
    for row_index,row in enumerate(cells[start:],start):
        for col_index,value in enumerate(row):
            text=str(value or '')
            tokens=re.findall(r'(?<![A-Za-z0-9])[+-]?\d+(?:\.\d+)?',text)
            if len(tokens)>1 and number(text) is None:
                issues.append({'code':'MULTIPLE_VALUES_IN_CELL','cell':[row_index,col_index],'raw':text,'reason':'结构可疑：多个数值挤入单格，需人工/视觉核对'})
    for col in spec.get('columns',[]):
        try:head=' '.join(cell_at(table,p) for p in col['header_cells'])
        except (KeyError,IndexError,ValueError):
            issues.append({'code':'HEADER_REFERENCE_INVALID','reason':'表头异常：映射引用超出原表结构'});continue
        head=head.replace('（','(').replace('）',')')
        if head.count('(')!=head.count(')'):
            issues.append({'code':'BROKEN_HEADER','header':head,'reason':'表头异常：括号或单位文本被拆断，需人工/视觉核对'})
    return issues


def norm(value):
    return re.sub(r'\s+', '', str(value))


def cell_at(table, position):
    if not isinstance(position, list) or len(position) != 2 or any(type(v) is not int or v < 0 for v in position):
        raise ValueError('Invalid zero-based cell position')
    return table['cells'][position[0]][position[1]]


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    temp.replace(path)
