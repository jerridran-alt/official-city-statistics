# 官方城市统计数据采集 Skill

A Codex skill for collecting original city statistics from official Chinese government publications.

帮助研究者从国家统计局、省级统计局、市县统计局和政府门户查找统计年鉴、公报及其他政府性质文件，保存原始证据，并按研究指标、版本和统计口径补充城市—年份面板。

## 内容

- `SKILL.md`：采集、核验、版本选择、行政区划与断点规则。
- `scripts/official_fetch.py`：静态目录提取、附件下载、原文件缓存、SHA256 校验和失败记录。
- `scripts/audit_candidates.py`：检查新增候选的字段、观察年、指标范围和核验声明。
- `references/`：GFPS 项目适配、提取后端及候选记录规范。
- `examples/`：最小配置和原数记录示例，不包含完整研究数据。
- `tests/`：可离线运行的功能测试。

两个脚本只依赖 Python 标准库，建议 Python 3.10 或更新版本。Crawl4AI、Playwright、Docling 和 OCR 是复杂页面、扫描件的可选后端，不是脚本必装依赖。

## 使用

将此仓库放入 Codex 的技能目录，并保持文件夹名称为 `official-city-statistics`。技能可用后，以 `$official-city-statistics` 调用，并说明项目目录、城市名单、数据年份和需要的指标。

GFPS 配置默认讨论 369 个研究单位、2011—2025 年。其他项目应提供自己的配置，不直接套用这组样本或年份。技能不附带 GFPS 的私有流水线程序，也不是能自动填满所有城市数据的一键数据库。

在仓库根目录测试静态采集：

```bash
python scripts/official_fetch.py --url https://www.lf.gov.cn/Item/156066.aspx --registry examples/official_hosts.json --output work/cache
```

核实网站身份后，在自己的域名注册表添加具体域名。示例域名表仅包含少数已知官网，不是全国官方来源的完整清单。脚本精确匹配域名，跨域重定向也需核实；链接提取不自动证明来源或数值正确。

核查候选字段：

```bash
python scripts/audit_candidates.py --records examples/candidate.json --scope examples/research_scope.json --output work/candidate.audit.json
python -m unittest discover -s tests -v
```

## 数据规则

采用官方原始统计值，按 `年鉴 > 公报 > 其他政府文件`，同类来源采用最新刊载版本。出版年与观察年分别记录，不将“2026 年出版”误认为不能提供 2025 年数据。

核对全市/市辖区范围、人口和就业口径、单位、能源范围、贷款币种及区划变更。空白不填零，不根据增长率反推金额，不用规上工业能源替代全社会能源。保留全部冲突来源，不取均值。

最终研究面板与来源审计分开保存。采集脚本不直接写 Excel；审核通过后由研究项目自身的入库和导出流程处理。

## 验证范围

静态网页采集、离线目录解析、缓存完整性和候选结构检查已经测试。候选审计只检查结构与核验声明，不能代替原文核实。没有验证全体政府网站的可访问性，也没有完成扫描件 OCR 的端到端准确性测试。

示例原数来自[廊坊市政府发布的 2025 年统计公报](https://www.lf.gov.cn/Item/156066.aspx)。它用于展示记录格式，不构成完整城市数据集。
