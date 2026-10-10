# 有进度下载与VPN分流

全局VPN必须保持开启以维持模型/API连接时，不能通过关闭VPN解决统计网站访问。仅把已经核实的统计局/政府文件域名配置为直连；模型/API和其他未列域名沿用用户原VPN出口。不替用户猜国内代理、关闭TLS校验、修改全局代理或操作系统路由。

## 单次HTTP直连

```text
python scripts/route_probe.py --url <一个已核实官方URL> --registry <发布者表.json> --output <诊断目录>
python scripts/official_fetch.py --url <官方URL> --registry <发布者表.json> --output <原件目录> --network-route direct --idle-timeout 25
```

`direct`只在这次请求建立`ProxyHandler({})`，绕过HTTP/系统代理，不改变环境变量或模型连接。但全局/TUN/VPN驱动仍可能接管该流量；**direct不保证国内IP**，成功只证明该URL可访问。`route_probe.py`并列保存configured/direct结果和证据，不根据412自动推断地区。若用户已确认地域限制，可在项目外部诊断记录`region_restriction_basis: user_confirmed`，不要对其他项目泛化。

若客户端提供“规则/智能分流/中国网站直连/排除域名”，保持VPN连接，将已核实官方域名加入DIRECT，保留其他流量原路径，再重新探测。具体菜单和规则导入格式须以实际客户端为准；不能把某个同名加速器假定成Shadowrocket或Clash。若客户端只提供全局隧道且无分流能力，Python代码无法保证绕过驱动；可改用用户授权、支持分流的既有客户端或单独国内网络采集端，不能宣称已经解决。

`assets/official-domains-direct.txt`由内置31省入口和城市网址的主机名生成，只供客户端白名单参考。每个项目只启用实际核实且需要的域名；提供地址不是本轮可访问证明。跨域CDN须核对官网真实链接与发布者后另加，不用全国IP段或关闭全局VPN替代。

用户已有授权国内HTTP(S)代理时支持`--network-route proxy --proxy-env <变量名>`。连接端点/凭据只放私有环境变量，不写入仓库或日志。模式在单次请求中生效；没有国内出口不猜地址、不自动购买服务。浏览器由当前环境允许的浏览器工具操作，不擅自切换为不允许的后台浏览器。

省级入口配置可设`network_route`及`proxy_env`；`collect_sources.py`支持同名命令行参数；`run_pipeline.py`读取项目`network: {route, proxy_env, idle_timeout, work_budget_seconds}`。不能只在单页测试使用新通道而实际批量流程仍用旧通道。Python采集脚本不依赖模型API，必要时可以在单独国内机器运行后带回原件与真实采集清单；是否临时关闭本机VPN由用户决定，技能不得自动断开模型连接。

## 下载进度与续传

- `--timeout`/`--idle-timeout`是无数据等待限制，**默认没有整个文件的统一截止时间**。持续收到字节就继续，并写入`.part`和`.progress.json`。
- 用户明确需要本轮工作配额时才加`--max-seconds`。它在读取边界检查，可能超出配额一个无进度等待窗口；到达配额保留部分原件而不是丢弃重下。
- 续传前检查部分文件字节数/SHA；只在有强ETag或Last-Modified时使用Range＋If-Range。206起点、总长及版本标识必须一致；200表示服务器未接受续传或文件已变，重新获取，避免把两版字节拼起来。
- 原站不支持Range或未提供版本标识时不能承诺续传；记录原因而不是假装成功。无进度超时、正文短于Content-Length、工作配额停止都保留待取任务；不生成完整原件清单、不向下游喂半个PDF。
- 完整正文、原文件SHA、捕获清单全部落盘后才清理部分文件。每次同表所有城市仍一起读取。
- 无进度/412时先切换已允许通道，避免同路径反复请求；可用合格归档并保留省级最新版本回查，不把失败来源称为无数据。

## 本轮验证边界

本地合成HTTP服务器验证：持续进度可超过idle timeout完成；工作配额保留字节且校验Range续传；无进度超时明确失败；不接受Range时不重复拼接；损坏部分文件拒绝续传；请求分流不改变全局环境。2026-10-10实际甘肃年鉴目录：configured与HTTP-direct都返回412；因此此环境的地域访问问题尚不能靠HTTP代理旁路解决。没有伪造国内IP成功案例。浏览器曾可读官网目录不代表所有附件都能下载。
