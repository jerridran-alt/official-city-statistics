# 采集与提取

长PDF先按[执行预算](execution-budget.md)用`pdf_probe.py`抽查正文，再从目录定位目标原页；封面文字不能证明正文有文字层。`run_pipeline.py`对超过5页且无页映射的PDF显式停止，避免盲OCR前5页。

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
- PDF文本表后端：需要 pdfplumber。**无边框文本PDF和复杂合并表头PDF不保证取数**；0表/0记录明确非零退出并标“未解析，非数据齐全”。列错乱、多值挤一格、碎裂括号/单位表头先隔离为结构可疑，不把解析失败当缺失占位跳过。改走PDF渲染＋OCR、官方HTML/XLSX或人工，不向下游喂空数据。

映射中的行列均从 0 开始。`header_cells` 必须支持指标、观察年、单位；`scope_quote`、`class_quote` 和 `edition_quote` 必须存在于原文。若年份/单位只在表外说明而不能满足映射，先调整提取后端/原表结构或人工建立可核查证据，不凭配置强填。

每张表先读取城市列中的全部城市，不以配置名单裁剪采集。省合计等非城市行和非数值占位另存报告；名单外城市保留原名称、原格及来源行ID，research_id 为 null，identity_status 为 unmapped。不能随意模糊匹配，也不能把“一行全市”与“一行市辖区”合并。缓存依据原文件哈希、格式、编码和解析器版本；同表用于下一城市、扩大研究名单或不同指标配置时复用结构，不重复 OCR。缓存校验失败会重新解析。

## OCR

若年鉴版年/名称只在目录，可用映射顶层 `context_chain` 指向证据根目录下的目录→章节网络清单。程序核验原件哈希、同官网及逐级导航，最后必须链接到候选原表；标题不能凭配置赋值。参见[江苏真实多城市例](jiangsu-validation.md)。表头仍直接从原表读取，脚注范围仍需审核。

```text
python scripts/ocr_image.py --input <扫描图或PDF> --output work/ocr_words.json --cache-dir work/ocr_cache --engine rapidocr
```


推荐 RapidOCR＋CPU ONNX Runtime。Windows 原生 OCR/Tesseract 是备用，必须检查语言及实际识别结果；本次北京原生OCR出现误读，不能把“后端可用”当准确。

`ocr_image.py` 现在接受图片或PDF；PDF先用pypdfium2渲染。默认最多5页，剩余页记录队列，可用 `--max-pages` 调整，不宣称全书已读完。缓存包括原文件、页面、词坐标和校验值；低分或无评分的词在 `ocr_review.html` 中标红，高分也必须看原图。

`ocr_extract.py` 对已覆盖的单城年份行和指标行布局自动找年、字段、单位和数值列，不用逐表行列 mapping。城市/版年由父发布页或书目路径推断并标需审核。多城市矩阵/跨页改用 `ocr_matrix.py` 的可审阅提案或显式页映射；真实存档验证及命令见[矩阵与受控跨页](matrix-extraction.md)。未映射的未知结构、半行续接、无城市列、混合口径仍待核，不猜值或补小数点。

正文可使用 `document_extract.py`，证据是原文字符范围和规则回放；跨区域、其他年份、人均与总量、就业流量与存量不得混用。领域规则未覆盖的字段列入报告，不断言官方没有数据。

完整有限路径：

```text
python scripts/run_pipeline.py --url <官方公报页> --config <项目配置> --registry <来源登记> --output work/case --media-limit 1 --ocr-engine rapidocr
```

直接官方PDF/图片可传 `--parent-url <原发布页>`，绑定附件链接、标题、数据年和发布日期。未解析、限额队列和候选审核状态保留在 `pipeline_report.json`；候选生成后仍需真实审核，再筛选导出。参见北京复现例。
