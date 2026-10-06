# 不依赖 Codex 的独立环境

基础 HTML/CSV/XLSX 解析用标准库；PDF/图像需要依赖。先诊断，不要先假定电脑装好了后端。

```text
python scripts/doctor.py
python scripts/bootstrap.py --venv .venv --profile ocr
```

`bootstrap` 创建独立虚拟环境，通过 PyPI 安装包，不修改系统 Python。`basic` 提供 PDF读取/渲染和 Pillow；`ocr` 增加 RapidOCR＋CPU ONNX Runtime；`test` 增加测试专用 ReportLab；`browser` 额外安装 Playwright 及 Chromium。镜像/网络访问失败应单独处理，不把未安装当作已安装。

安装后使用新环境的 Python，而不是继续用全局 Python：

- Windows PowerShell：`& .\.venv\Scripts\python.exe scripts/doctor.py`
- Linux/macOS：`.venv/bin/python scripts/doctor.py`

RapidOCR 中文后端在已安装时优先使用。Windows 原生 OCR 和 Tesseract 为备用；原生 OCR 需 Windows OCR 中文语言能力，Tesseract 需可执行文件和 `chi_sim`。这些不是同一个依赖，也不能用“有 Pillow”代替“有中文 OCR”。

`doctor` 检查包、语言及浏览器二进制，并明确哪些能力可用；包存在仍不是准确率认证。当前已在一个不继承 Codex 预装包的新 Windows 虚拟环境中安装并跑通北京验证；未据此声称所有操作系统或所有版式已验证。

完整 PDF 测试套件需要测试依赖。缺失时测试报错，不会跳过关键 PDF 用例后显示全绿：

```text
python scripts/bootstrap.py --venv .venv --profile test
```

然后用隔离环境 Python 运行 `-m unittest discover -s tests -v`。扫描/图片后端复现另需 `ocr` profile。
