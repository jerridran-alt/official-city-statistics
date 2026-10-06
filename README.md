# 官方城市统计数据采集 Skill

A configurable Codex skill for collecting original city statistics from official Chinese publications.

从官方年鉴、发展公报和政府文件采集来源、读取表格、核对证据并筛选版本。城市、年份、指标、优先级及交付格式由配置决定，不依赖 GFPS 或私有流水线。

**按表采集，按城市查缺。** 一张省级/全国表格读取一次，提取图表全部城市所需的数据，包含研究名单外城市，缓存原文件和结构化表格，后续城市复用缓存。

## 能力

| 脚本 | 功能 | 依赖/边界 |
|---|---|---|
| `official_fetch.py` | 单页/附件缓存、URL及SHA256记录、可选浏览器渲染 | HTTP为标准库；浏览器需Playwright及Chromium |
| `collect_sources.py` | 按深度和页面限额遍历统计目录 | 有限遍历，不保证整站完整 |
| `extract_tables.py` | HTML合并表头、CSV、XLSX、文本PDF表格；多城市原数抽取 | HTML/CSV/XLSX为标准库；PDF需pdfplumber；字段映射需要核对 |
| `ocr_image.py` | 扫描图OCR文字、坐标、置信度及图像哈希 | 需Tesseract及语言包；不能自动认证数字 |
| `audit_candidates.py` | 重读原文件，核对数值格、城市行、表头、上下文和采集清单 | 机械一致性检查，统计语义仍需审核 |
| `select_panel.py` | 单独审核后按配置优先级/版年筛选，输出JSON/CSV | 保留冲突及待核项，不估算、不换算单位 |

建议 Python 3.10+。不直接读取旧 `.xls`，不计算 XLSX 公式，不保证扫描件、图表及复杂无边框 PDF 可直接解析。可选浏览器/OCR后端未完成真实网站及真实扫描件端到端准确性验证。

## 离线快速体验

`examples/sample_table.html` 是明确标注的教学合成表，不含真实研究数值；包含三座城市和一个省合计，研究配置仅包含其中两座城市。

```bash
python scripts/extract_tables.py --input examples/sample_table.html --format html --config examples/project.json --mapping examples/table_mapping.json --output work/candidates.json --cache-dir work/table_cache --evidence-root .
python scripts/audit_candidates.py --records work/candidates.json --config examples/project.json --evidence-root . --registry examples/official_hosts.json --output work/audit.json
python -m unittest discover -s tests -v
```

第一条读取图表全部三座城市，生成六条原数候选；其中四条匹配当前研究名单，两条名单外原数仍保留，再次运行复用表格缓存。第二条核对原格及上下文；离线示例没有真实网络采集清单，**不能作为官方数据入库**。

## 实际项目

1. 创建项目配置：稳定研究ID、城市名称/明确别名、观察年份、原始指标。
2. 核实官网及发布者，维护来源注册表，按有限深度采集目录与附件。
3. 检查原表，配置表号、城市列、起始行、指标列和表头位置，一次抽取图表全部城市，再匹配研究名单。
4. 保存原文件，重读核验证据，单独记录来源、脚注及口径审核，再筛选导出。

当前需求的模板采用 **国家统计局 > 各省统计年鉴 > 发展公报 > 其他政府官方文件**，同级取最新版。其他研究者可修改，不是所有项目的强制来源顺序。

程序不会因几个核验布尔值为 true 就相信候选；它重读原文件并核对实际数据位置及采集清单。官网身份、版本类别、脚注语义仍有人工信任边界，见[证据规范](references/records.md)。配置见[项目配置](references/config.md)，PDF/OCR和采集命令见[提取后端](references/extraction.md)。

缓存、审核记录与最终面板分别保存。Excel等交付形式由用户项目选择，核心脚本不绑定私有导出器。

## 在 Codex 中使用

将仓库放入技能目录，文件夹名称保持 `official-city-statistics`，技能可用后以 `$official-city-statistics` 调用，并说明项目目录与配置。`SKILL.md` 是入口。

这是开发中的工具，没有大规模使用或OCR准确性保证。欢迎通过 [Issues](https://github.com/jerridran-alt/official-city-statistics/issues) 提供可公开的来源结构、问题和复现步骤；不要提交私人数据或凭据。
