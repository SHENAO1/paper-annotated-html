# paper-HTML

`paper-annotated-html` 是一个 Claude Code 技能，用来把学术论文 PDF 做成双栏批注精读 HTML。

## 目录

```
paper-annotated-html/      技能本体（SKILL.md、scripts/、assets/、references/、evals/）
*.pdf                      测试论文（不入库）
*_work/                    抽取与批注的工作目录（不入库）
*.annotated.html           生成结果（不入库，原文版权归作者，仅供个人学习）
```

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
用 paper-annotated-html 技能把 <论文.pdf> 做成双栏批注精读 HTML，一次做完。
```

## 手动运行脚本

```bash
python paper-annotated-html/scripts/extract_pdf.py paper.pdf          # 抽取到 <slug>_work/
python paper-annotated-html/scripts/build_html.py <slug>_work --check # 校验
python paper-annotated-html/scripts/build_html.py <slug>_work         # 构建
```

## 测试用例

`paper-annotated-html/evals/` 下有两个用例：一篇工程论文（设计验证型）和一篇人文社科论文（实证型）。用例所需的 PDF 放在各自的 `files/` 目录里，但不入库。在新机器上需要手动把 PDF 复制进去，文件名见各用例的 `prompt.md`。
