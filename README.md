# paper-annotated-html

把一篇学术论文 PDF 做成**双栏批注精读 HTML**的 Agent 技能：

- **左栏**：英文原文，按五类论证维度彩色高亮，每段下面附中文意译；
- **右栏**：逐段中文批注，包括段落功能、逻辑角色、论证技巧或漏洞；
- **页尾**：论证结构总览，包括逻辑骨架、一句话主张、最强处与最弱处、主张—证据对照和术语表。

生成的 HTML 是单个文件，可以离线打开，图表和公式都已内嵌。支持三种体裁：人文论证型、实证型、工程设计验证型。

> **English.** An agent skill that turns an academic paper (PDF) into a single offline HTML file for close reading: the English original with colour-coded argument highlights and a Chinese translation under each paragraph, Chinese margin notes on every paragraph, and an overview of the paper's argument structure. It uses the standard `SKILL.md` format, so it works in Claude Code, Codex, WorkBuddy and other agents that load skills from a folder.

## 安装

需要 Python 3.9+。

```bash
git clone https://github.com/SHENAO1/paper-annotated-html.git
cd paper-annotated-html
pip install -r paper-annotated-html/requirements.txt
python install.py
```

`install.py` 会找出本机装了哪些 Agent，把技能链接进它们的技能目录。用的是链接而不是复制，所以以后 `git pull` 一次，所有 Agent 就都更新了。装好后重启 Agent。

| Agent | 技能目录 | 只装这一个 |
|---|---|---|
| Claude Code | `~/.claude/skills/` | `python install.py --agent claude` |
| Codex | `$CODEX_HOME/skills/`（默认 `~/.codex/skills/`） | `python install.py --agent codex` |
| WorkBuddy | `~/.workbuddy/skills/` | `python install.py --agent workbuddy` |
| 其他 Agent | 它的技能目录 | `python install.py --dest <目录>` |

其他选项：

- `--list`：查看各 Agent 的安装状态；
- `--copy`：复制而不是链接，适用于不认链接的 Agent；
- `--uninstall`：卸载；
- `--dry-run`：只打印，不改动。

脚本不会删除它没装过的目录。那个位置已经有别的同名目录时，脚本会跳过；加 `--force` 则先把旧目录改名备份，再安装。

**不想用 git**：在 [Releases](https://github.com/SHENAO1/paper-annotated-html/releases) 下载 `paper-annotated-html-<版本>.zip`，解压到 Agent 的技能目录。也可以在支持上传技能的 Agent（比如 WorkBuddy 的技能页面）里直接上传这个 zip。

**不支持技能目录的 Agent**：在本仓库里打开它。根目录的 `AGENTS.md` 会告诉它按 `paper-annotated-html/SKILL.md` 的流程做。

## 使用

对 Agent 说一句话就行：

```
用 paper-annotated-html 技能把 papers/todo/<论文.pdf> 做成双栏批注精读 HTML，一次做完。
```

可以顺便告诉它课程信息（例如"课程：脉冲功率技术 · 第 6 周"），课程会显示在页头。技能会自己分批批注，并记录进度：中途断了，再说一次就从断点接着做。一篇二三十页的论文通常要写几十到上百段批注，所以最好用上下文较长、能连续工作的模型。

## 论文库

```
papers/
  todo/              未完成：放新论文；工作目录 <slug>_work/ 也在这里
  done/<slug>/       已完成：PDF、工作目录和 .annotated.html 放在一起
```

新论文放进 `papers/todo/`（或直接放在 `papers/` 下）。在论文库里做完一篇时，技能会自动归档。也可以手动整理：

```bash
python paper-annotated-html/scripts/organize_papers.py papers
```

**"已完成"的判定**：正式构建成功过，即工作目录里有 `built.json`，并且它记下的 HTML 就在 PDF 旁边。用 `--allow-partial` 或 `--sections` 生成的预览不算完成。加 `--dry-run` 只打印要移动什么。

## 版权

论文原文受版权保护，生成的 HTML 包含全文和图表，**只供个人学习**：

- 不要把 PDF 或生成的 HTML 公开发布，或提交到公开仓库。`.gitignore` 已经排除了这些文件；
- 要分享，就只分享批注和总览，或者用开放获取（OA）论文。

## 手动运行脚本

```bash
S=paper-annotated-html/scripts
python $S/extract_pdf.py paper.pdf                 # 抽取到 <slug>_work/
python $S/build_html.py <slug>_work --status       # 进度和下一步
python $S/build_html.py <slug>_work --check        # 只校验
python $S/build_html.py <slug>_work                # 正式构建
python $S/organize_papers.py papers                # 整理论文库
```

## 开发

```
paper-annotated-html/   技能本体（SKILL.md、scripts/、assets/、references/、evals/），可以单独分发
install.py              安装到各 Agent
tools/package.py        打包成 dist/paper-annotated-html-<版本>.zip（不含 evals）
tests/                  冒烟测试，用的是自编的示例论文
papers/                 论文库（只有目录结构入库）
```

```bash
python -m unittest discover -s tests -v
python tools/package.py
```

`paper-annotated-html/evals/` 里有两个完整的评测用例：一篇工程论文（设计验证型）和一篇人文社科论文（实证型）。用例要用的 PDF 有版权，不随仓库提供，需要自己下载后放进各用例的 `files/` 目录，并按 `prompt.md` 里的文件名改名：

- `marx-generator.pdf`：*Fast and Flexible, Arbitrary Waveform, 20-kV, Solid-State, Impedance-Matched Marx Generator*，IEEE Transactions on Plasma Science，2023，DOI [10.1109/TPS.2023.3235418](https://doi.org/10.1109/TPS.2023.3235418)；
- `fairy-tale-values.pdf`：*Values That Are Explicitly Present in Fairy Tales: Comparing Samples from German, Italian and Portuguese Traditions*，Journal of Data Mining and Digital Humanities，2024。

发版步骤见 `AGENTS.md`，改动记录见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

代码以 [MIT](LICENSE) 许可发布。依赖 [PyMuPDF](https://pymupdf.readthedocs.io/) 采用 AGPL-3.0 许可，由用户自行安装，本仓库不包含它。
