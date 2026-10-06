# GFPS 项目约定

- 项目根目录由当前工作区或用户指定，不固定机器路径。
- 369 个研究单位，2011—2025 年，共 5,535 行；稳定 ID 来自已确认名单，不用当前行政代码表重新生成研究名单。
- 按行政代码升序逐城补缺：北京、天津、石家庄……来源检查完但仍缺值时不能宣称城市完整。
- 以 `work/research_variable_scope.json` 的 `keep_indicators` 为准，包括 GDP、就业、投资、能源、用电、人口、产业、财政科技、贷款等原始指标。不同口径及单位保留区别，不换算、估算或计算效率、资本存量。
- 官方原数按来源类别及最新版选定；来源优先级不是中央网站一定高于省市网站。冲突证据全部保留，不因冲突舍弃可用官方数据。
- `outputs/城市年份原始数据面板_369城市_2011-2025.xlsx` 仅一个城市—年份面板工作表，无额外颜色、图表、公式、说明列或来源工作表。来源、区划、质量标记外部保存。

## 现有流水线

在项目根目录先核实脚本仍存在及字段含义：

1. `work/additional_official_records.json` 保存原始补录；`source_rank` 映射须通过程序确认，不凭数字大小猜测。
2. `work/prepare_verified_supplements.py` 合并补录。
3. `work/prepare_plain_panel.py` 筛选面板原数并保存选择审计。
4. `work/build_plain_panel.mjs` 导出表格。
5. `work/validate_plain_panel.py` 核验行数、单位名单、年份、值和格式。

新增候选采用明确 `source_class`，并不替代旧 `source_rank`；入库前核对映射，不要求旧记录迁移或清空。断点 `work/sequential_collection_progress.json` 会变化，技能不写死当前城市。
