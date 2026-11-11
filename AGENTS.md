# AGENTS.md

本仓库是 `paper-annotated-html` 技能：把学术论文 PDF 做成双栏批注精读 HTML。这份文件写给在本仓库里工作的 AI Agent（Codex、Claude Code、WorkBuddy 等）。

## 用户让你处理论文时

- 按 [`paper-annotated-html/SKILL.md`](paper-annotated-html/SKILL.md) 的流程做，即使你的 Agent 没有把它当作已安装的技能加载。文中的 `$SKILL` 就是 `paper-annotated-html/` 目录。
- 论文放在 `papers/todo/`，做完后运行 `python paper-annotated-html/scripts/organize_papers.py papers`，把它归档到 `papers/done/`。
- 依赖：`pip install -r paper-annotated-html/requirements.txt`。

## 修改本仓库时

- **不要提交论文内容**：PDF、`*_work/`、`*.annotated.html` 都受版权保护，`.gitignore` 已排除，不要用 `git add -f` 绕过。测试只用 `tests/fixture/` 里自编的文字。
- **改脚本后跑测试**：`python -m unittest discover -s tests -v`。
- **技能目录要能单独分发**：`paper-annotated-html/` 会被链接或复制进各 Agent 的技能目录，也会被打包成 zip，所以它里面的文件不能依赖仓库根目录的任何东西。
- **SKILL.md 保持各 Agent 通用**：frontmatter 只用 `name`、`description`、`license`、`metadata`；正文里提到某个 Agent 才有的工具时，写成"如果有就用"。
- **发版**：改 `paper-annotated-html/SKILL.md` 里的 `metadata.version`，在 `CHANGELOG.md` 记一条，然后 `python tools/package.py` 生成 `dist/` 里的 zip。
