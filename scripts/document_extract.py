"""Literal indicator extraction from official article prose; no per-document table mapping."""
import argparse,hashlib,json,re
from pathlib import Path
from document_source import read_article,infer_context
from failure_types import classify,SourceFailure
from stats_core import number,save

NUM=r'(?P<value>[+-]?\d[\d,]*(?:\.\d+)?)'
MONEY=r'(?P<unit>万亿元|亿元|万元|元)'
POP=r'(?P<unit>万人|人)'
PERCENT=r'(?P<unit>%)'
RULES={
 '地区生产总值':r'(?<!人均)地区生产总值\s*'+NUM+r'\s*'+MONEY,
 '第二产业增加值':r'第二产业增加值\s*'+NUM+r'\s*'+MONEY,
 '第三产业增加值':r'第三产业增加值\s*'+NUM+r'\s*'+MONEY,
 '工业增加值':r'(?:全年(?:实现)?|全市(?:实现)?)工业增加值\s*'+NUM+r'\s*'+MONEY,
 '年末常住人口':r'年末(?:全市)?常住人口(?:\[\d+\])?\s*'+NUM+r'\s*'+POP,
 '城镇常住人口':r'城镇人口\s*'+NUM+r'\s*'+POP,
 '常住人口城镇化率':r'(?:城镇化率(?:为)?|占常住人口的比重为)\s*'+NUM+r'\s*'+PERCENT,
 '地方一般公共预算支出':r'(?:全市)?一般公共预算支出(?:完成)?\s*'+NUM+r'\s*'+MONEY,
 '全社会用电量':r'全社会用电量(?:为|达到)?\s*'+NUM+r'\s*(?P<unit>亿千瓦时|万千瓦时|千瓦时)',
 '全社会能源消费总量':r'(?:全市|全社会)能源消费总量(?:为)?\s*'+NUM+r'\s*(?P<unit>万吨标准煤|吨标准煤)',
 '金融机构本外币贷款余额':r'金融机构(?:（含外资）|\(含外资\))?本外币各项贷款余额\s*'+NUM+r'\s*'+MONEY,
 '金融机构人民币贷款余额':r'人民币各项贷款余额\s*'+NUM+r'\s*'+MONEY,
 '地区生产总值增长率':r'(?<!人均)地区生产总值\s*\d[\d,.]*\s*(?:万亿元|亿元|万元)[^。；\n]{0,75}?(?:比上年|同比)(?P<direction>增长|下降)\s*'+NUM+r'\s*'+PERCENT,
 '固定资产投资增长率':r'(?:全年)?固定资产投资(?:（不含农户）|\(不含农户\))?[^。；\n]{0,20}?(?:比上年|同比)(?P<direction>增长|下降)\s*'+NUM+r'\s*'+PERCENT
}


def extract_article(file,config,root,capture_manifest):
    root=Path(root).resolve();file=Path(file).resolve();capture_path=Path(capture_manifest).resolve()
    capture=json.loads(capture_path.read_text(encoding='utf-8-sig'))
    article=read_article(file,capture['final_url']);context=infer_context(article,config)
    if not config['years'][0]<=context['year']<=config['years'][1]:raise SourceFailure('OBSERVATION_OUT_OF_SCOPE','标题数据年不在项目观察区间；应换用匹配年份来源')
    if not article['main_region_detected']:raise SourceFailure('ARTICLE_REGION_UNCERTAIN','未确定正文边界，不能从导航或推荐链接猜测指标')
    records=[];unsupported=[];excluded_mentions=[]
    for indicator in config['keep_indicators']:
        if indicator not in RULES:unsupported.append(indicator);continue
        for match in re.finditer(RULES[indicator],article['text']):
            paragraph_start=article['text'].rfind('\n',0,match.start())+1
            prefix=article['text'][paragraph_start:match.start()][-120:]
            explicit_years=re.findall(r'(20\d{2})年',prefix)
            if explicit_years and int(explicit_years[-1])!=context['year']:
                excluded_mentions.append({'indicator':indicator,'quote':match.group(0),'char_start':match.start(),'reason':'数据年份不匹配：段落明确引用其他年份'});continue
            foreign_subject=any(v in prefix for v in ('京津冀','长三角','珠三角','全国','全省'))
            own_subject=any(v in prefix[-35:] for v in ('全市',context['city']+'实现',context['city']+'完成'))
            if foreign_subject and not own_subject:
                excluded_mentions.append({'indicator':indicator,'quote':match.group(0),'char_start':match.start(),'reason':'地域不匹配：正文引用跨区域/全国/全省数据，不是标题城市的同口径原数'})
                continue
            raw=match['value'];value=number(raw)
            if value is None:continue
            if match.groupdict().get('direction')=='下降':value=-abs(value)
            source_row=hashlib.sha256((article['source_sha256']+str(match.start())).encode()).hexdigest()[:24]
            identity=json.dumps([article['source_sha256'],context['research_id'],context['year'],indicator,match.start(),match.end(),capture['final_url']],ensure_ascii=False)
            records.append({'id':hashlib.sha256(identity.encode()).hexdigest()[:24],'research_id':context['research_id'],'source_row_id':source_row,'identity_status':'matched','city':context['city'],'year':context['year'],'indicator':indicator,'unit':match['unit'],'value':value,'source_class':context['source_class'],'edition':context['edition'],'geographic_scope':'全市','is_derived':False,'evidence':{'kind':'article_span','file':file.relative_to(root).as_posix(),'sha256':article['source_sha256'],'capture_manifest':capture_path.relative_to(root).as_posix(),'capture_url':capture['final_url'],'char_start':match.start(),'char_end':match.end(),'quote':match.group(0),'rule_id':indicator,'value_raw':raw,'title':context['title'],'publication_date':context['publication_date']},'review_requirements':['发布者与标题城市','数据年份和统计范围','原数及单位']})
    return {'records':records,'context':context,'missing_indicators':[n for n in config['keep_indicators'] if n not in {r['indicator'] for r in records}],'unsupported_rules':unsupported,'excluded_mentions':excluded_mentions,'images':article['images'],'data_complete':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input','config','evidence-root','capture-manifest','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args()
    try:
        config=json.loads(Path(a.config).read_text(encoding='utf-8-sig'));result=extract_article(a.input,config,a.evidence_root,a.capture_manifest)
        failed=not result['records'];status='unparsed' if failed else 'extracted_candidates'
        if result['records']:save(a.output,result['records'])
        save(a.output+'.report.json',{k:v for k,v in result.items() if k!='records'}|{'status':status,'records':len(result['records'])})
        print(json.dumps({'status':status,'records':len(result['records']),'missing_indicators':result['missing_indicators'],'image_sources':len(result['images'])},ensure_ascii=False))
        return 1 if failed else 0
    except Exception as exc:
        report={'status':'unparsed','records':0,'data_complete':False,'failure':classify(exc)};save(a.output+'.report.json',report);print(json.dumps(report,ensure_ascii=False));return 1


if __name__=='__main__':raise SystemExit(main())
