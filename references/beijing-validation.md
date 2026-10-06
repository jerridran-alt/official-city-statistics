# 北京真实来源验证（2026-10-07）

来源：[北京市2025年国民经济和社会发展统计公报](https://tjj.beijing.gov.cn/zxfbu/202603/t20260324_4564401.html)，及该页面直接发布的[表1原图](https://tjj.beijing.gov.cn/zxfbu/202603/W020260326350033499259.jpg)。元数据发表于2026年，观察年2025。

## 实际结果

- 新建独立 Windows 虚拟环境，无继承 Codex 预装库，安装基础包、RapidOCR 和 CPU ONNX 后运行。
- 获取真实文章、定位正文及嵌入图片。旧表格后端对此 HTML 未识别到结构化表格；新正文通路获得12条原数候选。
- 中文 OCR 从表1原图识别四个金额：GDP 52073.4亿元、第二产业7187.4亿元、第三产业44776.9亿元、工业6126.5亿元。无手填行列 mapping；原图视觉核对后与正文一致。
- 总计16条候选，原文/图像证据核验通过16条；本轮由 Codex 做原文/视觉复核，单独保存审核记录。去重筛选得到12项指标，导出北京市2025年的一行CSV。不是对全部指标的认证，研究者仍需最终复核。
- 正文引用的京津冀区域GDP 11.99万亿元及其增长率被排除；没有把就业流量当作就业存量。
- 2025能源消费总量和全社会用电量本轮未取得；未用发电占比、其他年份或估算值填补。
- 冷启动这一有限路径约19.375秒，含网络、正文和一幅图片OCR；图片OCR约13.859秒。不是所有文件或每1000值的统一性能指标。

## PDF 验证边界

将同一官方GDP图片生成零文字层的**衍生测试PDF**，文字提取长度为0。PDF渲染＋OCR读出了上述四个金额，用于检验扫描路由。副本不是官方原PDF，不冒充新的政府附件，也未作为新的官方来源入库。

另有三类必跑PDF回归：无边框文本PDF明确失败、带框碎裂合并表头被隔离、正常多列表格正确取数。此结果不等于复杂扫描PDF已经全部可靠。

Windows 原生 OCR 在同一验证中出现部分字符/数字误读，不能凭“后端可用”自动入库。RapidOCR也必须检查原图；高分只用于安排复核顺序，不当作字形真值。

## 复现

先按[环境指引](environment.md)安装 `ocr` profile。使用该环境 Python：

```text
python scripts/run_pipeline.py --url https://tjj.beijing.gov.cn/zxfbu/202603/t20260324_4564401.html --config examples/beijing_project.json --registry examples/beijing_authorities.json --output work/beijing --media-limit 1 --ocr-engine rapidocr
```

检查 `pipeline_report.json`、`candidates.json`、`audit.json` 和OCR原图/坐标。完成真实审核、建立 `reviews.json` 后：

```text
python scripts/select_panel.py --records work/beijing/candidates.json --config examples/beijing_project.json --evidence-root work/beijing --registry examples/beijing_authorities.json --reviews work/beijing/reviews.json --output work/beijing/selected.json
python scripts/export_panel.py --input work/beijing/selected.json --output work/beijing/panel.csv
```

图片限额为1是本次有限验证的边界，其他来源仍在队列，不是只读图中某几个城市或宣布所有数据齐全。
