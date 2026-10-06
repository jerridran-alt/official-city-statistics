"""Explicit coverage boundaries; a successful reference case does not certify a layout family."""
import re


def coverage():
    return {
        'real_reference_cases':[
            {'case':'北京市2025公报正文','verified_outputs':12,'scope':'该文已支持规则及原句；不代表全部公报模板'},
            {'case':'北京市2025公报GDP单图','verified_outputs':4,'scope':'该单页指标行布局及四个金额；不代表全部图片/布局'}
        ],
        'derived_fixture_cases':[{'case':'同图生成的零文字层PDF','scope':'渲染/OCR路由测试，不是官方原PDF，不认证其他扫描件'}],
        'synthetic_regressions':['HTML/CSV/XLSX及多城市合成表','无边框/碎裂合并表头/正常多列PDF'],
        'not_real_end_to_end_validated':['复杂跨页表','多城市扫描矩阵','未覆盖布局','全体政府站点/浏览器动态页面','其他OCR引擎与操作系统组合'],
        'default_for_uncovered_layouts':'pending_review_no_automatic_panel_import',
        'general_reliability_claim':False
    }


def boundary(layout,config):
    pages=layout.get('pages',[])
    if len(pages)>1:
        return {'code':'MULTIPAGE_LAYOUT_NOT_VALIDATED','reason':'多页的独立表/跨页续表关系尚未验证，先标待核；禁止自动拼接或将北京单图结果泛化。'}
    if layout.get('pages_queued',0):
        return {'code':'INCOMPLETE_PAGE_COVERAGE','reason':'还有未处理页，无法判定跨页表结构；来源待核，不当作已解析全书。'}
    names=set()
    generic={'全市','全省','全区','市辖区','地区','自治州','全国','合计','总计'}
    configured=[u['name'] for u in config.get('units',[])]
    for p in pages:
        for word in p.get('words',[]):
            text=re.sub(r'\s+','',word.get('text',''))
            # Conservative detection: explicit administrative labels or multiple
            # configured city names. This is a stop signal, not an entity resolver.
            if text in configured:names.add(text)
            if re.fullmatch(r'[\u3400-\u9fff]{1,20}(?:自治州|地区|市|县|区|盟|旗)[①②③④⑤*]*',text) and text not in generic:names.add(text)
    if len(names)>1:
        return {'code':'MULTICITY_SCAN_LAYOUT_NOT_VALIDATED','detected_labels':sorted(names),'reason':'检测到多城市/行政单元扫描标签，当前OCR自动解释未通过真实矩阵验证；保留全部OCR词与原图，转待核，不套用单城上下文。'}
    return None
