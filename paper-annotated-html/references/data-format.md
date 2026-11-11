# 数据格式

`build_html.py` 读取工作目录里的三类文件。所有文件都是 UTF-8 JSON。

```
<slug>_work/
├── source.json        原文（extract_pdf.py 生成，校对时直接改）
├── figures/*.png      图表截图
└── annot/
    ├── meta.json      全文级：体裁、中文标题、术语表、论证总览
    └── S0.json …      每节一个：每个条目的高亮、译文、批注
```

## source.json（原文）

```json
{
  "proofread": true,
  "meta": {"title": "...", "authors": "...", "venue": "...", "year": "2023", "doi": "...", "front_text": "..."},
  "sections": [
    {"id": "S1", "title": "I. INTRODUCTION", "level": 1, "items": [
      {"id": "S1.P1", "kind": "para", "text": "…原文逐字…", "page": 2},
      {"id": "S3.P1", "kind": "para", "runin": "Data collection.", "text": "Data collection. We sampled …"},
      {"id": "F1", "kind": "figure", "page": 2, "bbox": [x0, y0, x1, y1], "image": "figures/F1.png", "caption": "Fig. 1. …"},
      {"id": "TI", "kind": "table", "image": "figures/TI.png", "caption": "TABLE I …"},
      {"id": "S10.E3", "kind": "equation", "number": "1", "raw": "P = V I cos φ (1)", "latex": ""}
    ]}
  ]
}
```

- `proofread`：校对完成后由你加上 `true`。`--status` 据此判断是否进入批注阶段。
- `level`：1 = 一级章节（进入顶部章节导航），2/3 = 小节。
- `kind`：`para` 段落、`keywords` 关键词行、`figure`、`table`、`equation`。
- `keywords` 条目放进摘要所在的节，不要单独成节，否则章节导航里会多出一个"关键词"。
- `runin`（可选）：段首的行内小标题，比如 "Data collection." 或 "A. Setup."。它必须与 `text` 的开头逐字相同，渲染时加粗。不要把它从 `text` 里删掉。
- 校对时可以合并、拆分、删除条目，也可以改 `text`。**id 一旦开始写批注就不要再改**，因为批注靠 id 对应。新增条目自己起一个不重复的 id（如 `S3.P2b`）。
- `meta.authors / venue / year` 抽取时常为空，校对时从首页补全（显示在页头）。
- `⟨?⟩` 是抽取失败的字形（常见：Ω、μ、≤、希腊字母），必须对照页面图改掉，否则构建报错。

## annot/meta.json（全文级）

```json
{
  "profile": "design",
  "title_zh": "论文标题的中文译名",
  "course": "课程名 · 第 N 周",
  "authors": "可选，覆盖 source.json 的值",
  "glossary": [
    {"term": "transmission line", "aliases": ["TL", "TLs"], "zh": "传输线", "def": "一句话释义"}
  ],
  "overview": {
    "skeleton": {
      "problem":    {"text": "1–3 句", "refs": ["S1.P4"]},
      "claim":      {"text": "…", "refs": ["S2.P3"]},
      "evidence":   {"text": "…", "refs": ["S5.P2", "F7"]},
      "rebuttal":   {"text": "…", "refs": ["S8.P1"]},
      "conclusion": {"text": "…", "refs": ["S9.P1"]}
    },
    "thesis":    {"zh": "作者核心主张一句话", "en": "可选：英文原句或自拟英文"},
    "strongest": {"text": "论证最强处", "refs": ["…"]},
    "weakest":   {"text": "论证最弱处", "refs": ["…"]},
    "claims": [
      {"claim": "主张", "evidence": "支撑它的证据", "strength": "strong|medium|weak", "refs": ["…"]}
    ]
  }
}
```

- `profile`：`argument` / `empirical` / `design`，见 `dimensions.md`。决定图例文字和骨架五步的名称。
- `course` 为空时页头只显示体裁徽章。
- `glossary`：红色高亮的短语如果包含某个 term 或 alias（整词匹配，不区分大小写），鼠标悬停会显示 `zh + def`。术语表也会出现在总览末尾。
- `refs` 可以写条目 id（`S3.P2`、`F4`、`TI`）或节 id（`S5`），会渲染成可点击跳转的链接。写错 id 会报错。
- `skeleton` 的五个键固定，缺一个就报错。
- `claims` 可选，建议写 3–6 条。
- `overview_final`（meta.json 顶层字段）：全部段落批注完、总览修订完之后设为 `true`（第 5 步）。在此之前总览视为草稿。

## annot/S{n}.json（每节一个）

```json
{
  "section": "S1",
  "title_zh": "引言",
  "summary": "可选：本节一两句话概括，显示在节标题下",
  "items": {
    "S1.P2": {
      "hl": [
        ["state of charge (SOC)", "red"],
        ["this is the quantity our estimator is designed to track", "yellow"]
      ],
      "zh": "整段中文译文（纯文本）",
      "note": {
        "func": "收窄到应用对象",
        "role": "在论证链中的位置……",
        "craft": "论证技巧……",
        "gap": "潜在漏洞……",
        "stage": "problem"
      }
    },
    "S0.K2": {"hl": [], "zh": "关键词：……"},
    "F1": {"zh": "图 1　图注译文", "note": {"func": "…", "role": "…", "craft": "…", "stage": "evidence"}},
    "TI": {"zh": "表 I　表题译文", "table": {"header": ["参数", "设计值"], "rows": [["额定电压", "400 V"]]}},
    "S10.E3": {"latex": "P = V I \\cos\\varphi", "zh": "可选：公式含义说明"}
  }
}
```

### 各类条目

| kind | 必填 | 可选 |
|---|---|---|
| para | `hl`、`zh`、`note`（func、role、stage，craft 与 gap 至少一项） | — |
| keywords | `zh` | `hl` |
| figure | `zh`（图注译文） | `note`（关键结果图建议写） |
| table | `zh`（表题译文） | `table`（把表格转写成 HTML 表，原截图折叠在下方）、`note` |
| equation | — | `latex`（强烈建议）、`zh`（公式含义） |

- `hl` 每项是 `[短语, 颜色]`。短语必须**从 `source.json` 的 `text` 中逐字复制**；构建时先精确匹配，再在忽略空白差异和弯直引号差异后匹配；同一短语出现多次时，取第一个不与已有高亮重叠的位置。
- 颜色只能是 `yellow`、`red`、`blue`、`green`、`purple`。
- 高亮之间不能重叠，也不能嵌套。
- `zh` 和 `note` 中的各字段都是纯文本，不要写 HTML 或 Markdown。
- `note.stage` 只能取 `problem` / `claim` / `evidence` / `rebuttal` / `conclusion`。
- 批注卡片左边的颜色取该段高亮覆盖字数最多的那一色，所以卡片颜色就是这段的主色调。
- `latex` 不要写 `$`，编号由 `number` 自动加 `\tag{}`。行内数学可以直接写在 `zh` 里，用 `\( … \)` 包起来，KaTeX 会渲染。

## 构建与校验

```bash
python scripts/build_html.py WORK_DIR --status                      # 进度、分批方案和下一步该做什么
python scripts/build_html.py WORK_DIR --dump S4-S6                  # 打印这几节校对后的原文（带条目 id）
python scripts/build_html.py WORK_DIR --check                       # 只校验，不输出文件
python scripts/build_html.py WORK_DIR --allow-partial --sections S0-S2 --out WORK_DIR/preview.html
python scripts/build_html.py WORK_DIR                               # 正式构建 → <pdf目录>/<标题>.annotated.html
```

**错误**（必须修复，否则不写出文件）包括：

- 缺批注、缺译文、缺 note 字段，或 stage 不合法；
- 高亮短语在原文中找不到，或颜色不合法；
- 原文中残留 `⟨?⟩`；
- 总览缺项，或 refs 指向不存在的 id；
- JSON 语法错误。

**警告**（逐条判断，不必清零）包括：

- 译文长度与原文不成比例：汉字数与英文词数之比低于 0.9，可能漏译；高于 3.2，可能注水；
- 译文里残留没翻译的英文小写单词。括号、引号、方括号引文和 `\( \)` 行内公式里的词不算，带连字符的词和术语表里的词也不算。需要保留的术语，写成"中文（English）"；作为研究对象被讨论的英文词（语料词、检索词），加引号写成“faith”；
- 某节只有关键词，应并入摘要所在的节；
- 单段高亮超过 5 处，或覆盖超过 40% 的字数；
- 某种颜色全文都没用过；
- 超过 35% 的段落没有高亮；
- 同一句 craft 重复出现；
- 公式没有写 LaTeX。
