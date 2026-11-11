# 更新记录

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-11-11

首个公开版本。

### 新增

- `paper-annotated-html` 技能：把论文 PDF 做成双栏批注精读 HTML（英文原文五色高亮 + 中文意译 + 逐段批注 + 论证结构总览），支持人文论证型、实证型、工程设计验证型三套维度。
- `extract_pdf.py`：抽取 PDF 文本、页面图和图表截图，支持单栏和双栏版式，可单独重截某张图。
- `build_html.py`：分批进度（`--status`）、按节打印原文（`--dump`）、校验（`--check`）、预览（`--allow-partial --sections`）和正式构建；正式构建成功后写 `built.json` 作为完成标记。
- `organize_papers.py`：把论文库分成 `done/`（已完成）和 `todo/`（未完成）。
- `install.py`：一条命令把技能装到 Claude Code、Codex、WorkBuddy 的技能目录。
- `tools/package.py`：打包成可上传的 zip。
- 冒烟测试与 GitHub Actions（Windows / macOS / Linux）。

[0.1.0]: https://github.com/SHENAO1/paper-annotated-html/releases/tag/v0.1.0
