# 同输入效率验证

每100个实际新增值继续作为项目主指标，同时报告核对值数、新增率、重复/修订数、来源格式、缓存状态、网络失败与等待。不能只比较不同省份的主指标就声称新版提速或退步。

改版本后先回放**相同原件、映射、待补键与审核要求**，结果字段/证据/待核必须相同；再分别测相同URL的获取路径。热缓存与首次OCR分别列出。原件回放改善不能推广为境外网络获取改善；合成下载测试不能冒充真实官方下载。

按原件SHA＋映射/项目配置＋审核身份复用已核验缓存。同一批原文件只校验一次，同一OCR工件只读取一次，任务结束再确认原件未变。统计范围、源字节、版次、字段映射、审核有变化时失效；不能为了速度跳过最新重刊或已发现旧值错误。

选表前使用`collection_efficiency.py`的`expected_keys`对照已有键。已有测量的预计成本可提供`estimated_seconds`，同省同层优先预计新增/秒高的表；未知成本仍需检查元数据，不能把估计当实测。`newer_eligible_edition`、`scope_changed`、`same_source_correction_due`保留版本复核优先级。**选表是排工作顺序，不是只读取缺失城市或取消低新增表。**

首次`PhaseLedger`立即持久化起点。实际读图/映射等跨工具步骤可用：

```text
python scripts/execution_control.py --ledger <账本.json> --start-phase visual_review --label table1 --output <开始.json>
python scripts/execution_control.py --ledger <账本.json> --finish-phase --label table1 --output <结束.json>
```

`mapping`、`visual_review`、`machine_audit`、`selection`、`export`分别记录；机器核验不等于人工复核。未结束阶段在`open_phases`显示；未归属间隙不自动算作模型推理。并行阶段用区间并集，不能把重叠网络时间从总时间直接扣掉声称收益。
