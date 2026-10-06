# 官方城市统计数据采集 Skill

A configurable Codex skill for collecting original city statistics from official Chinese publications.

**MIT 开源：任何人都可以免费使用、修改、分发和商用，无需向作者申请或另外授权。** 保留版权声明和[许可证](LICENSE)即可。此许可适用于本仓库代码与文档；外部依赖、模型和官方原文件遵循各自的许可或发布规则。

从官方年鉴、发展公报及政府文件采集原始统计数值，保存来源与位置，核对城市/年份/单位/范围，再筛选和导出城市年份数据。项目自行配置样本、变量、年份与优先级，不绑定私有流水线。

**按表采集，按城市查缺。** 已解析图表中的全部城市先进入来源缓存，研究名单只在入库时筛选；名单外城市保留原名与证据，未知代码不猜。复杂扫描矩阵未解析时明确排入待核，不能声称已读齐全。

## 已修复的失败防御

- 0表格、0记录、0数据行明确非零退出，提示“未解析，非数据齐全”。不会把空结果或旧输出交给下游当成功。
- 行列错乱、多值挤一格、碎裂括号/单位表头先隔离为结构可疑。
- 必跑PDF回归涵盖无边框文本、碎裂合并表头和正常多列表格；缺测试依赖报错，不以跳过PDF得到全绿。
- 网络、解析、环境、匹配资格错误分类，网络有界重试，解析失败换后端。

## 验证范围

**真实验证范围** 当前真实端到端覆盖包括北京2025公报正文、GDP一张单页指标行图片，以及江苏2025年鉴表9-10的13城市用电量HTML表；扫描PDF使用同图生成的测试副本。复杂跨页、多城市扫描矩阵和未覆盖布局仍待核，不能泛化。详见[验证覆盖矩阵](references/coverage.md)，运行报告也包含该范围。

## 能力与边界

|入口|用途|边界|
|---|---|---|
|`doctor.py` / `bootstrap.py`|诊断并建立独立环境|不依赖Codex预装库；系统/语言仍需检查|
|`official_fetch.py` / `collect_sources.py`|官方页/附件、哈希、缓存、有限目录遍历|不保证整站可访问或完整|
|`extract_tables.py`|HTML/CSV/XLSX/文本PDF表格|字段映射＋结构自检；无边框/复杂PDF不保证取数|
|`document_extract.py`|公报正文的原句、字位和已支持指标规则|自动识别标题城市/数据年；排除跨区域、人均/总量混淆等；未覆盖规则明确报告|
|`ocr_image.py` / `ocr_layout.py`|图片/扫描PDF渲染＋中文OCR、词坐标、缓存、低分报告|推荐RapidOCR＋CPU ONNX；识别分数不是字形真值|
|`ocr_extract.py`|已覆盖的单城年份行/指标行图自动找字段、年、单位和数值列|仍需视觉复核；复杂跨页、多城市扫描矩阵及混合口径待适配，不猜值|
|`run_pipeline.py`|连接官方获取、正文/图片候选和证据核验|有界媒体/页数，保留未处理队列；候选不自动批准|
|`audit_candidates.py`|重读原文或回放OCR证据、核对采集链|三个自填核验布尔值不赋予信任；统计语义仍需真实审核|
|`select_panel.py` / `export_panel.py`|审核后选版本，输出原数JSON/城市年份CSV|先匹配再排来源；不换单位、不估算、不填零|

**无边框文本PDF和复杂合并表头PDF，pdfplumber路径不保证取数。** 0表或结构可疑必须停止该路径，标待人工/OCR，改用渲染OCR、官方HTML/XLSX或人工；不得向下游喂空数据。扫描件不是文本表后端的支持承诺。

## 独立环境与真实北京例

建议Python 3.10+。先诊断，再安装需要的profile，安装不修改系统Python。

```bash
python scripts/doctor.py
python scripts/bootstrap.py --venv .venv --profile ocr
```

之后使用隔离环境的Python。Windows PowerShell：

```powershell
& .\.venv\Scripts\python.exe scripts/run_pipeline.py --url https://tjj.beijing.gov.cn/zxfbu/202603/t20260324_4564401.html --config examples/beijing_project.json --registry examples/beijing_authorities.json --output work/beijing --media-limit 1 --ocr-engine rapidocr
```

Linux/macOS同一命令将开头替换为 `.venv/bin/python`。本次实际验证运行于Windows新环境；不据此保证所有操作系统已测试。

结果包含`candidates.json`、`audit.json`、`pipeline_report.json`、原文件、OCR位置和审核图；请查看原文/原图，建立真实`reviews.json`后：

```text
python scripts/select_panel.py --records work/beijing/candidates.json --config examples/beijing_project.json --evidence-root work/beijing --registry examples/beijing_authorities.json --reviews work/beijing/reviews.json --output work/beijing/selected.json
python scripts/export_panel.py --input work/beijing/selected.json --output work/beijing/panel.csv
```

以上`python`指新环境的Python，不是尚未装依赖的全局解释器。直接官方PDF/图片可传`--parent-url`绑定原发布页。

[北京真实验证](references/beijing-validation.md)：官方正文获得12条候选，GDP原图OCR获得4条，源证据核验16条；本轮由Codex实际做原文/视觉核对并记录审核，去重得到12项原数，导出北京市2025年一行CSV。京津冀区域GDP被排除，2025能源总量/全社会用电量本轮仍未取得。**这是有限小样本验证，不是全指标、全城市或OCR准确率保证。**

同一官方图片生成的零文字层测试PDF也走通渲染/OCR，副本不冒充官方原PDF或新来源。Windows原生OCR出现误读，仍作为可用备用通路，不能据“可用”自动批准。

## 合成表体验与测试

真实省级多城市例：[江苏统计年鉴2025表9-10](references/jiangsu-validation.md)，一次提取13城×2018—2024共91个全社会用电量原数。首轮只配置2城仍保留其余77值，扩大名单复用缓存；原表排除网损等脚注完整保留，不用省合计替代各市值。

```text
python examples/validate_jiangsu.py --output work/jiangsu_reference
```

本例只依赖标准库；联网失败或原件改版明确失败，扫描矩阵/复杂跨页仍待核。结果为可核验JSON，demo身份不是正式研究行政代码。

```text
python scripts/extract_tables.py --input examples/sample_table.html --format html --config examples/project.json --mapping examples/table_mapping.json --output work/candidates.json --cache-dir work/table_cache --evidence-root .
```

合成图表含3城市，研究名单只有2城市；仍读取全部3城共6值，名单外城市也保存。不是研究数据。

运行完整测试：

```text
python scripts/bootstrap.py --venv .venv --profile test
```

然后使用隔离环境Python执行`-m unittest discover -s tests -v`。当前46项测试在独立环境中全部实际执行，无跳过；另有江苏真实91格参考例，不包含浏览器真实网站的全面验证。

## 来源与口径

当前模板：**国家统计局 > 各省统计年鉴 > 发展公报 > 其他政府官方文件**，同级取最新刊载版本。只在城市、数据年、指标和统计范围匹配的原数之间比较；高等级来源没有城市分项时继续查地方来源，不用全国数替代。出版年与观察年分别记录。其他用户可改优先级。

环境见[安装与诊断](references/environment.md)，配置见[项目配置](references/config.md)，操作见[提取后端](references/extraction.md)，核验边界见[证据规范](references/records.md)。来源身份登记和语义审核仍有人工信任边界，不是防伪认证。

将仓库放入技能目录，目录名保持`official-city-statistics`，通过`$official-city-statistics`调用，说明项目与配置。欢迎通过[Issues](https://github.com/jerridran-alt/official-city-statistics/issues)反馈可公开来源结构与复现步骤；请勿上传私人数据或凭据。
