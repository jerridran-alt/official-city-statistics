# 目录与提取后端

`official_fetch.py` 只依赖 Python 标准库。核实官网后在项目外部 JSON 注册精确域名：

```json
{"hosts": [{"host": "www.lf.gov.cn", "publisher": "廊坊市人民政府", "evidence_url": "https://www.lf.gov.cn/", "verified": true}]}
```

子域名、跨站附件、重定向目标分别核实。域名表不是完整官方站点清单，也不是统计真实性判断；不要将第三方镜像注册为官方来源。

```text
python <skill>/scripts/official_fetch.py --url https://www.lf.gov.cn/Item/156066.aspx --registry work/official_hosts.json --output work/city_sources/langfang/cache
python <skill>/scripts/official_fetch.py --url https://www.lf.gov.cn/Item/156066.aspx --registry work/official_hosts.json --output work/city_sources/langfang/cache --html work/skill_pilot/comm_page.html
```

第二条离线解析已有 HTML。路径按调用目录解释，`<skill>` 替换为安装目录。默认复用 URL 缓存；需要新版本时加 `--refresh`。保存原始文件、SHA256、时间和链接；目录链接仅作线索。默认 25 秒超时、最多一次重试、100 MiB 限制，可用参数调整。脚本不递归、不执行网页 JS，不提取统计数值。

- Crawl4AI/Playwright 用于必须渲染或点击的目录，不以返回网页证明表格完整。
- Docling native 无需模型，但不重建表格、不保证阅读顺序、不对图片图表 OCR。
- 文字层可能将数字拆出空白；整理文字后仍须核对负号、单位、观察年。
- 扫描件/OCR 核查数字、符号、行列、合并表头和脚注，保存页码和图像。依赖未安装时列入待提取，不声称已测试。
- 年鉴“本年”可能是数据年，不是封面出版年，先看编制说明。

静态目录采集及缓存已经测试。Crawl4AI/Docling 模型和扫描件 OCR 未完成端到端准确性验证，使用前应对目标网站与文件做小范围测试。
