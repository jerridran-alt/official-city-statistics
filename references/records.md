# 证据核验与版本选择

V2 候选由 `extract_tables.py` 生成，包含图表全部城市的原数。匹配研究名单者带稳定 research_id，未匹配者保留原名称、source_row_id、identity_status=unmapped 和 research_id=null，不猜代码。记录还包含城市、观察年、指标、原单位/原数、文献类别、版年、地域范围及 `evidence`。证据包含相对原文件路径、SHA256、格式、表号、城市格、数值格、表头格、原格字符串和原文上下文。缺少这些证据时，三个旧核验标志即使全为 true 也不会通过。

```text
python scripts/audit_candidates.py --records work/candidates.json --config examples/project.json --evidence-root . --registry examples/official_hosts.json --output work/audit.json
```

程序重新读取原文件，不信任候选的数值或缓存矩阵：检查哈希、实际数值格、同一城市行、配置别名、表头中的指标/年/单位，以及原文范围、类别和出版年引用。同一批次的同一文件只重新读取一次。网络采集清单也必须与原文件、URL、发布者和外部注册表一致。

`machine_checks_passed` 只表示上述一致性检查通过。`origin.capture_matched` 表示原数能关联到一致的网络采集清单与已登记来源；未提供清单、离线参考或未核实来源不能凭布尔声明得到该状态。注册表本身仍需外部身份核查，清单不是防伪签名。

脚注含义、出版类别、行政边界和原表统计口径另行审核。单独的审核文件是 JSON 数组：

```json
[{"record_id": "抽取生成的ID", "source_sha256": "原文件校验值", "decision": "approve", "reviewer": "实际审核者", "reason": "原表标题、脚注和城市范围的具体核查依据"}]
```

不得伪造审核者或复制空泛批准理由。记录和审核意见分开，以保留原始证据与决策轨迹；这不是对审核者独立性或统计真实性的自动证明。

```text
python scripts/select_panel.py --records work/candidates.json --config examples/project.json --evidence-root . --registry examples/official_hosts.json --reviews work/reviews.json --output work/selected.json --csv work/selected.csv
```

筛选器按研究名单从已采集全部城市中筛选，名单外记录只排除出当前面板，仍保存在来源缓存与 excluded_from_panel 报告。筛选器再次核查原文，一致网络采集与审核缺一不可；原文件改变后旧审核失效。未审核、证据不符、同级同版冲突均保留为待核/冲突，退出码 1，不生成健康的“全齐”结论。输出不换算单位，不计算效率，不将缺失补零。原数数据与审核表分离，最终项目面板格式由用户决定。

## V3 正文与OCR证据

正文候选使用 `article_span`：绑定原文件、正文字符范围、原句、标题、出版日期和已登记规则；审核脚本独立重读并回放，改值/改单位/改身份不能通过。

OCR候选使用 `ocr_layout`：原文件哈希、OCR工件哈希、页码、数值/表头/年份词索引，以及父发布页或书目上下文。审核程序检查采集链和回放位置解释，但 `glyph_accuracy_certified=false`，仍须查看原图。OCR候选不得凭三个旧布尔值或识别置信度自动批准。

矩阵候选使用 `ocr_matrix`，增加原页城市词、跨页表头锚点和 `matrix_plan/plan_sha256`。审核程序重读计划与原件并回放；审核决定还须绑定相同 `plan_sha256`，改计划后旧审核失效。`partial_pending` 上游阻断下游，即使已输出部分候选也不当成功。真实离线存档模式 `archived_original` 不冒充新网络清单，`origin.capture_matched=false`，不得自动正式入库。见[矩阵流程](matrix-extraction.md)。

上游报告为unparsed或empty_or_error时，审核CLI阻断空数据与旧输出；空审核输入、空选择、空面板不返回成功。失败区分network、parse、environment及eligibility，有界网络重试，解析/配置问题先换后端或核对源。

选择后可运行 `export_panel.py --input selected.json --output panel.csv`，生成城市—年份宽表。单位写在列名，金额和比例不换算；目标缺项仍留空，导出成功不等于全样本齐全。
