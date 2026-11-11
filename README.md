# paper-HTML

`paper-annotated-html` 是一个 Claude Code 技能，用来把学术论文 PDF 做成双栏批注精读 HTML。

## 目录

```
paper-annotated-html/      技能本体（SKILL.md、scripts/、assets/、references/、evals/）
papers/                    论文库（只有目录结构入库，里面的论文和结果都不入库）
  todo/                    未完成：还没用技能做完的论文，工作目录 <slug>_work/ 也在这里
  done/<slug>/             已完成：PDF、工作目录和 .annotated.html 放在一起
```

PDF、`*_work/` 和 `*.annotated.html` 都不入库（原文版权归作者，仅供个人学习）。

## 论文库

新论文放进 `papers/todo/`（或直接放在 `papers/` 下）。每次做完一篇，运行：

```bash
python paper-annotated-html/scripts/organize_papers.py papers
```

脚本把论文分成两部分：

- **已完成**：正式构建成功过（工作目录里有 `built.json`，且它记下的 HTML 在 PDF 旁边）。PDF、工作目录和 HTML 一起移到 `papers/done/<slug>/`。
- **未完成**：其余的都留在或移到 `papers/todo/`，并显示进度（未开始、待校对、批注中）。

`--allow-partial` 或 `--sections` 生成的预览不算完成。加 `--dry-run` 只打印要移动什么，不实际移动。技能在论文库里做完一篇时会自己运行这一步。

引入 `built.json` 之前构建的论文没有这个标记，会被当作未完成；在工作目录上重新运行一次 `build_html.py` 就会补上。

## 安装

技能源码放在本仓库里，通过目录联接（junction）装到用户技能目录：

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\paper-annotated-html" -Target "E:\Code\paper-HTML\paper-annotated-html"
```

在 Mac 上用软链接：

```bash
ln -s ~/Code/paper-HTML/paper-annotated-html ~/.claude/skills/paper-annotated-html
```

WorkBuddy 用同样的 SKILL.md 格式，技能目录是 `~/.workbuddy/skills`，同样用联接：

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.workbuddy\skills\paper-annotated-html" -Target "E:\Code\paper-HTML\paper-annotated-html"
```

如果 WorkBuddy 不认联接，就在它的技能页面上传 `dist/paper-annotated-html.zip`（不含 evals，需要时重新打包）。

依赖：`pip install pymupdf pillow`

一句话即可启动，技能会自己用 `build_html.py --status` 分批、断点续做：

```
用 paper-annotated-html 技能把 papers/todo/<论文.pdf> 做成双栏批注精读 HTML，一次做完。
```

## 手动运行脚本

```bash
python paper-annotated-html/scripts/extract_pdf.py paper.pdf          # 抽取到 <slug>_work/
python paper-annotated-html/scripts/build_html.py <slug>_work --check # 校验
python paper-annotated-html/scripts/build_html.py <slug>_work         # 构建
python paper-annotated-html/scripts/organize_papers.py papers         # 整理论文库
```

## 测试用例

`paper-annotated-html/evals/` 下有两个用例：一篇工程论文（设计验证型）和一篇人文社科论文（实证型）。用例所需的 PDF 放在各自的 `files/` 目录里，但不入库。在新机器上需要手动把 PDF 复制进去，文件名见各用例的 `prompt.md`。
