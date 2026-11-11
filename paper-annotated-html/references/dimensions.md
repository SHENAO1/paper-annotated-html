# 五色维度与体裁

五种颜色固定不变，但每种颜色标什么，取决于论文属于哪种体裁。先选体裁，再按该体裁的定义来标。图例文字和总览骨架五步的名称都来自 `assets/profiles.json`，写入 `meta.json` 的 `profile` 字段后会自动切换。

## 1. 选体裁

看论文**主要靠什么让读者相信它的结论**：

| 体裁 | 主要依靠 | 典型领域 |
|---|---|---|
| `argument` 论证型 | 推理、概念辨析、文本与案例解读 | 哲学、理论、法学、政策评论、文学批评、综述性论证 |
| `empirical` 实证型 | 对现实世界数据的收集与分析 | 社会科学、心理学、医学、计算人文、带数据分析的 CS 论文 |
| `design` 设计验证型 | 造出一个东西（电路、系统、算法、装置），再测它 | 电气、电子、机械、系统、算法设计与实验验证 |

拿不准时这样判断：

- 论文有"我们造了 / 提出了 X，并测得 Y"的结构，选 `design`。
- 论文有"我们收集了数据 D，分析发现 Y"的结构，选 `empirical`。
- 其余选 `argument`。
- 计算人文类论文（用语料、模型或统计方法回答人文问题）属于 `empirical`；只做文本细读和理论阐释的人文论文属于 `argument`。

在给用户的说明里写一句选了哪种体裁、为什么。

## 2. 通用高亮原则

- **少而准。** 每段 2–4 处，最多 5 处。读者只看高亮就应该能抓住这段在论证里做了什么。不要把整句或整段都涂上颜色，覆盖率超过 40% 会触发警告。
- **标短语，不标整句。** 一般 3–15 个英文词。要截取信息最密的那一截：比如标 "smaller classes improve reading scores"，而不是把它所在的整句都标上。
- **逐字复制。** 短语必须从 `source.json` 的 `text` 中原样复制，包括连字符、弯引号和大小写。
- **一色一义。** 拿不准用哪种颜色时，问自己"读者为什么要注意这几个词"：
  - 因为这是作者要证明的东西 → 黄；
  - 因为不懂这个词就读不下去 → 红；
  - 因为它是支撑某个主张的事实或数字 → 蓝；
  - 因为它限制、让步或反驳 → 绿；
  - 因为它说明了作者是怎么做或怎么论证的 → 紫。
- **黄色只给作者自己的主张。** 引用别人的观点不标黄。如果作者拿它当证据，标蓝；如果作者反对它，标绿。
- **红色标术语的定义处或第一次关键使用处**，不要每次出现都标。缩写定义（如 "random forest (RF)"）连同括号一起标。
- **不单独标**引文编号、图号或套话（"In this paper"、"As shown in Fig. 3"）。
- **颜色分布要合理。** 某种颜色全文一次都没用会触发警告；这时要回头确认论文是否真的没有这一维度。例如工程论文几乎一定有局限或权衡，应当有绿色。
- 有些段落确实无可标（纯过渡、致谢式的段落），可以 `"hl": []`，但这样的段落不应超过三分之一。

## 3. 三种体裁的颜色定义

### argument 论证型

| 色 | 图例 | 标什么 | 信号词 / 例子 |
|---|---|---|---|
| 黄 | 核心论点 | 全文论点、各节分论点、中间结论 | "I argue that…", "this shows…", "the point is…" |
| 红 | 关键概念 | 作者定义或重新界定的概念，理解论证必须掌握的术语 | "what I call X", "by X I mean…", 斜体或加引号的概念 |
| 蓝 | 证据与例证 | 文本引证、历史事实、案例、思想实验、引用的研究结论 | "for example", "consider…", "according to…" |
| 绿 | 让步与反驳 | 预设的反对意见、作者的让步、对他人观点的反驳、自承局限 | "one might object…", "admittedly", "however", "it does not follow that…" |
| 紫 | 方法与论证路径 | 论证策略和推理结构：类比、归谬、概念分析、谱系考察、限定论证范围 | "by analogy with…", "suppose for reductio…", "I proceed in three steps" |

### empirical 实证型

| 色 | 图例 | 标什么 | 信号词 / 例子 |
|---|---|---|---|
| 黄 | 研究问题与核心发现 | 研究问题、假设、主要发现、对贡献的声明 | "we ask whether…", "our findings suggest…", "Our claim is that…" |
| 红 | 关键概念与构念 | 理论构念、操作化定义、专门的方法术语 | "perceived social support", "topic coherence score" |
| 蓝 | 数据与结果 | 样本和语料规模、统计量、效应方向、具体结果 | "N = 1,200", "p < .01", "the distance between X and Y is smaller in…" |
| 绿 | 局限与替代解释 | 局限、替代解释、效度威胁、结论的适用边界、与既有发现的冲突 | "a limitation is…", "this may also reflect…", "preliminary", "hint at" |
| 紫 | 研究设计与方法 | 抽样、变量、模型、分析流程、三角互证、可复现性措施 | "we sampled…", "we coded the interviews…", "we triangulate…", "a fine-tuned BERT model" |

### design 设计验证型

| 色 | 图例 | 标什么 | 信号词 / 例子 |
|---|---|---|---|
| 黄 | 核心主张与贡献 | 设计目标、声称的贡献或新颖性、"能做到 X"的主张 | "We developed…", "this allows…", "significantly improved" |
| 红 | 关键术语与参数 | 器件和拓扑名称、关键参数的定义、指标的含义 | "field-oriented control (FOC)", "1.2-kV breakdown voltage" |
| 蓝 | 实验与测量数据 | 测量值、仿真结果、与目标的数值对比 | "98.1% peak efficiency", "settling time below 2 ms at full load" |
| 绿 | 局限、权衡与对比 | 未达标项、设计折中、和其他方案的比较、留给未来的问题、限定的适用范围 | "at the cost of higher switching loss", "We focus only on…", "Future work will…" |
| 紫 | 设计与实验方法 | 设计决策及其理由、电路和结构的做法、测试方法与测试条件 | "modeled as a lumped RC network", "measured with a 1-GHz differential probe" |

## 4. 常见误区

- 把每个数字都标蓝。只标**支撑某个主张**的数字；纯背景参数不标，或者在它是关键参数时标红。
- 把 "we propose a method" 标紫。**提出了什么**标黄，**方法怎么做**才标紫。
- 把所有 "however" 所在的句子都标绿。只有当它真正限制或反驳了某个主张时才标；单纯的语气转折不算。
- 只用黄和红，蓝、绿、紫很少出现。这说明读得太浅：证据、局限和方法恰恰是精读最该看清的部分。
