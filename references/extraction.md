# 采集与提取

## 来源采集

```text
python scripts/official_fetch.py --url <官方页面> --registry <来源注册表> --output <证据目录>
python scripts/collect_sources.py --url <年鉴目录> --registry <来源注册表> --output <证据目录> --depth 1 --limit 10
```

默认 HTTP，仅用标准库。清单记录 URL、最终 URL、发布者、网络/离线模式、时间、文件及 SHA256。默认缓存复用，必要时 `--refresh`。遍历最多两层、最多 100 个来源；结果记录尚未访问队列，不能据此宣称官网资料齐全。PDF/XLSX 附件走 HTTP。

动态页可用 `--engine browser --wait-selector table`，需要 Playwright 及 Chromium。浏览器模式保存渲染后 DOM，不冒称原始 HTTP 正文；默认不使用用户登录 Cookie。该适配器尚未完成真实网站端到端测试。当前环境若只允许指定浏览器工具，使用该工具取得允许的页面内容，不以脚本绕过限制。

## 结构化表格与多城市

```text
python scripts/extract_tables.py --input examples/sample_table.html --format html --config examples/project.json --mapping examples/table_mapping.json --output work/candidates.json --cache-dir work/table_cache --evidence-root .
```

- HTML：展开 rowspan/colspan 并保存原起始格；嵌套表格明确报错，需要适配。
- CSV：保留原单元格字符串，按明确表头映射读取。
- XLSX：标准库读取共享字符串/内联字符串及原存储数值；不计算公式。公式单元格，以及百分比、日期、缩放显示格式进入待核，不把存储值误当成显示值录入。旧 `.xls` 不支持直接解析，需要额外读取后端。
- PDF：需要 pdfplumber，读取文本型 PDF 的表格及页码；没有表格时明确报告，而不是猜测。扫描 PDF、复杂无边框表格、图表不是此后端的保证覆盖范围。

映射中的行列均从 0 开始。`header_cells` 必须支持指标、观察年、单位；`scope_quote`、`class_quote` 和 `edition_quote` 必须存在于原文。若年份/单位只在表外说明而不能满足映射，先调整提取后端/原表结构或人工建立可核查证据，不凭配置强填。

每张表先读取城市列中的全部城市，不以配置名单裁剪采集。省合计等非城市行和非数值占位另存报告；名单外城市保留原名称、原格及来源行ID，research_id 为 null，identity_status 为 unmapped。不能随意模糊匹配，也不能把“一行全市”与“一行市辖区”合并。缓存依据原文件哈希、格式、编码和解析器版本；同表用于下一城市、扩大研究名单或不同指标配置时复用结构，不重复 OCR。缓存校验失败会重新解析。

## OCR

```text
python scripts/ocr_image.py --input <扫描图> --output work/ocr_words.json --language chi_sim+eng
```

需要 Tesseract 和相应语言包，输出文字、坐标、置信度、源图哈希。无依赖时明确失败，不声称进行了 OCR。输出仅待视觉核查的识别结果，不能直接进入筛选器；需核对原图、行列、年份、单位、符号和脚注。当前没有完成真实扫描件 OCR 准确性验证。
