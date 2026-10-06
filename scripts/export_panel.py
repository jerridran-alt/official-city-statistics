"""Create a plain city-year CSV from selected original records without unit conversion."""
import argparse,csv,json
from pathlib import Path
from stats_core import save
from failure_types import SourceFailure,classify


def export(selected,path):
    if not selected:raise SourceFailure('NO_PANEL_ROWS','0 条可用原数，不能导出空面板并宣称成功')
    columns=sorted({(r['indicator'],r['unit'],r['geographic_scope']) for r in selected})
    groups={}
    for r in selected:
        key=(r['research_id'],r['city'],r['year']);group=groups.setdefault(key,{})
        col=(r['indicator'],r['unit'],r['geographic_scope'])
        if col in group and group[col]!=r['value']:raise ValueError('Unresolved conflicting originals cannot be flattened into one cell')
        group[col]=r['value']
    headers=['城市','年份']+[n+'（'+u+('，'+scope if scope!='全市' else '')+'）' for n,u,scope in columns]
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(headers)
        for key,values in sorted(groups.items()):writer.writerow([key[1],key[2]]+[values.get(c,'') for c in columns])
    return {'status':'panel_exported','city_year_rows':len(groups),'indicator_columns':len(columns),'derived_values':0,'data_complete':False,'note':'已选择原数的城市年份 CSV；缺项留空，不证明目标样本或指标已全部齐全。'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    try:
        data=json.loads(Path(a.input).read_text(encoding='utf-8-sig'));result=export(data['selected'],a.output);save(a.output+'.report.json',result);print(json.dumps(result,ensure_ascii=False));return 0
    except Exception as exc:
        result={'status':'unparsed','data_complete':False,'failure':classify(exc)};save(a.output+'.report.json',result);print(json.dumps(result,ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
