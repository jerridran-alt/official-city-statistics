"""Explicit coverage boundaries; a successful reference case does not certify a layout family."""
import re


def coverage():
    return {
        'real_reference_cases':[
            {'case':'北京市2025公报正文','verified_outputs':12,'scope':'该文已支持规则及原句；不代表全部公报模板'},
            {'case':'北京市2025公报GDP单图','verified_outputs':4,'scope':'该单页指标行布局及四个金额；不代表全部图片/布局'},
            {'case':'江苏统计年鉴2025表9-10分地区全社会用电量','verified_outputs':91,'scope':'真实HTML单表13城×2018—2024；目录证据链、全城采集及名单扩大缓存复用，不代表扫描矩阵或全部省份'}
        ],
        'real_archived_source_cases':[
            {'case':'河北2025年鉴8-8用电量扫描图','verified_outputs':90,'scope':'15个原始城市/脚注口径标签×6年，原图逐格参考一致；本轮官网超时，仅存档OCR验证，无新网络入库资格'},
            {'case':'重庆2025年鉴20-1及续表3，原PDF593/596页','verified_outputs':78,'scope':'39行政/限定口径标签×户籍及常住人口，原文行核对；只有年份继承，指标和单位来自各页，非任意跨页拼接保证'}
        ],
        'derived_fixture_cases':[{'case':'同图生成的零文字层PDF','scope':'渲染/OCR路由测试，不是官方原PDF，不认证其他扫描件'}],
        'synthetic_regressions':['HTML/CSV/XLSX及多城市合成表','无边框/碎裂合并表头/正常多列PDF'],
        'not_real_end_to_end_validated':['无城市列/半行断裂的续表','未映射或未知复杂跨页/多城市扫描布局','扫描矩阵新网络获取到正式研究面板的完整导入','全体政府站点/浏览器动态页面','其他OCR引擎与操作系统组合'],
        'default_for_uncovered_layouts':'pending_review_no_automatic_panel_import',
        'general_reliability_claim':False
    }


def boundary(layout,config):
    pages=layout.get('pages',[])
    if len(pages)>1:
        return {'code':'MULTIPAGE_LAYOUT_NOT_VALIDATED','reason':'单城解析路径没有矩阵/续表映射，先标待核；可改走ocr_matrix.py并核对原页身份/表头，不套用北京单图或按行号拼接。'}
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
        return {'code':'MULTICITY_SCAN_LAYOUT_NOT_VALIDATED','detected_labels':sorted(names),'reason':'检测到多城市标签，单城路径不适用；保留全部OCR词与原图，使用已核对的ocr_matrix映射或转待核，不套用单城上下文。'}
    return None
