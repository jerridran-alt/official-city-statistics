# 新增候选 JSON 数组

```json
[
  {
    "research_id": "131000",
    "city": "廊坊市",
    "year": 2025,
    "indicator": "固定资产投资增长率",
    "unit": "%",
    "value": -7.2,
    "source_class": "communique",
    "edition": 2026,
    "publisher": "廊坊市人民政府",
    "url": "https://www.lf.gov.cn/UploadFiles/jrlf/2026/6/202606041647452973.pdf",
    "publication_url": "https://www.lf.gov.cn/Item/156066.aspx",
    "locator": "PDF第1页，四、投资，正文首句",
    "original_text": "全年固定资产投资同比下降7.2%",
    "geographic_scope": "全市",
    "official_verified": true,
    "value_verified": true,
    "scope_verified": true,
    "is_derived": false
  }
]
```

`source_class` 为 `yearbook`、`communique` 或 `government_document`；`edition` 可超过面板最后数据年。`research_id` 为稳定 ID，历史代码/区划事件另外保存。核验标记分别表示来源、数值单位年月、地域口径已实际核对，不由采集成功自动赋值。`is_derived` 必须 false；明确刊载零才填零，空白/破折号不生成数值记录。

```text
python <skill>/scripts/audit_candidates.py --records work/new_candidates.json --scope work/research_variable_scope.json --output work/new_candidates.audit.json
```

存在问题则退出码 1，不能只取合格部分后声称批次通过。脚本不自动选版本，不生成 Excel。旧记录无需为此规范立刻迁移。
