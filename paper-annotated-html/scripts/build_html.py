#!/usr/bin/env python3
"""Build the annotated two-column HTML from a work directory.

    python build_html.py WORK_DIR [--out paper.html] [--allow-partial] [--sections S0,S1,S3-S5] [--check]
    python build_html.py WORK_DIR --status          progress per batch + the next action
    python build_html.py WORK_DIR --dump S4-S6      proofread text of these sections, with item ids

Inputs (all inside WORK_DIR):
    source.json        proofread source text (from extract_pdf.py, then corrected)
    figures/*.png      figure / table crops referenced by source.json
    annot/meta.json    profile, Chinese title, course, glossary, overview
    annot/S<n>.json    one file per section: highlights, translation and note per item

--check          validate only, write nothing
--allow-partial  items without annotation render as English + a "pending" card (for previews)
--sections       render only these sections (ids or ranges by position), e.g. S0-S2
Exit code 1 when validation finds errors (see references/data-format.md for the format).
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
MISSING = "⟨?⟩"
CJK = re.compile(r"[㐀-鿿]")
EN_WORD = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
CAP_PREFIX = re.compile(r"^((?:Fig\.|Figure|Fig|TABLE|Table|Scheme|Chart)\s*(?:[0-9]+|[IVXL]+)\s*[.:|]?)\s*", re.I)
SEC_NUM = re.compile(r"^((?:[IVXL]+|[0-9]+(?:\.[0-9]+)*|[A-Z])\.?)\s+")


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


# ------------------------------------------------------------------ loading
def load_json(p: Path, errors: list, required=True):
    if not p.exists():
        if required:
            errors.append(f"missing file: {p}")
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{p.name}: invalid JSON at line {e.lineno} col {e.colno}: {e.msg}")
        return None


def select_sections(sections, spec: str | None):
    if not spec:
        return sections
    ids = [s["id"] for s in sections]
    keep = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            if a in ids and b in ids:
                keep.update(ids[ids.index(a): ids.index(b) + 1])
        elif part in ids:
            keep.add(part)
    return [s for s in sections if s["id"] in keep]


# ------------------------------------------------------------------ highlights
_NORM = {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "‐": "-", " ": " "}


def _normalise(s: str):
    """Collapse whitespace and unify quotes/dashes; return text + map back to original indices."""
    out, idx = [], []
    prev_space = False
    for i, ch in enumerate(s):
        ch = _NORM.get(ch, ch)
        if ch.isspace():
            if prev_space:
                continue
            ch, prev_space = " ", True
        else:
            prev_space = False
        out.append(ch.lower())
        idx.append(i)
    return "".join(out), idx


def find_spans(text: str, hls, where: str, errors: list):
    """[[phrase, color, (optional) tip], ...] -> sorted non-overlapping (start, end, color, phrase)."""
    spans = []
    norm, idx = _normalise(text)

    def free(a, b):
        return all(b <= s or a >= e for s, e, *_ in spans)

    for h in hls:
        if not isinstance(h, list) or len(h) < 2:
            errors.append(f"{where}: highlight must be [phrase, color]: {h!r}")
            continue
        phrase, color = h[0], h[1]
        found = None
        start = 0
        while True:  # exact match first
            i = text.find(phrase, start)
            if i < 0:
                break
            if free(i, i + len(phrase)):
                found = (i, i + len(phrase))
                break
            start = i + 1
        if not found:
            pn, _ = _normalise(phrase)
            pn = pn.strip()
            start = 0
            while pn:
                i = norm.find(pn, start)
                if i < 0:
                    break
                a, b = idx[i], idx[i + len(pn) - 1] + 1
                if free(a, b):
                    found = (a, b)
                    break
                start = i + 1
        if not found:
            errors.append(f"{where}: highlight not found verbatim in the English text: {phrase!r}")
            continue
        spans.append((found[0], found[1], color, phrase))
    return sorted(spans)


def glossary_tip(phrase: str, tips: dict):
    """Exact glossary term first, else the longest term/alias that occurs as whole words in the phrase."""
    p = phrase.lower().strip()
    if p in tips:
        return tips[p]
    for term in sorted(tips, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", p):
            return tips[term]
    return None


def render_en(text: str, spans, tips: dict, runin: int = 0) -> str:
    """runin > 0 bolds text[:runin] (a run-in heading); a highlight crossing that boundary ends the bold early."""
    k = runin
    for a, b, *_ in spans:
        if a < k < b:
            k = a
    out = ['<b class="runin">'] if k > 0 else []
    open_b = k > 0

    def plain(x, y):
        nonlocal open_b
        if open_b and x <= k <= y:
            open_b = False
            return esc(text[x:k]) + "</b>" + esc(text[k:y])
        return esc(text[x:y])

    pos = 0
    for a, b, color, phrase in spans:
        out.append(plain(pos, a))
        tip = glossary_tip(phrase, tips) if color == "red" else None
        attrs = f' data-tip="{esc(tip)}" tabindex="0"' if tip else ""
        out.append(f'<mark class="hl {esc(color)}"{attrs}>{esc(text[a:b])}</mark>')
        pos = b
    out.append(plain(pos, len(text)))
    return "".join(out)


# ------------------------------------------------------------------ images
def embed_image(path: Path, warnings: list) -> str:
    data = path.read_bytes()
    mime = "image/png"
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.load()
        if im.width > 1500:
            im = im.resize((1500, round(im.height * 1500 / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        if im.convert("RGB").getcolors(maxcolors=6000) is None:  # photo-like -> JPEG
            im.convert("RGB").save(buf, "JPEG", quality=84, optimize=True)
            mime = "image/jpeg"
        else:
            im.save(buf, "PNG", optimize=True)
        if len(buf.getvalue()) < len(data):
            data = buf.getvalue()
        else:
            mime = "image/png"
    except ImportError:
        pass
    except Exception as e:  # keep the original bytes
        warnings.append(f"{path.name}: could not optimise image ({e})")
    return f"data:{mime};base64," + base64.b64encode(data).decode()


# ------------------------------------------------------------------ validation helpers
RESIDUE_SKIP = re.compile(r"（[^）]*）|\([^)]*\)|“[^”]*”|\"[^\"]*\"|‘[^’]*’|「[^」]*」|《[^》]*》|\\\(.*?\\\)|\[[^\]]*\]")
RESIDUE_WORD = re.compile(r"(?<![A-Za-z0-9\-_/.])[a-z]{3,}(?![A-Za-z0-9\-_/])")
RESIDUE_OK = {"etc", "via", "http", "https", "www", "com", "org", "pdf", "html"}
RESIDUE_FIX = ("translate them; English words discussed as words (corpus items, keywords) go in quotes “faith”; "
               "a term that must stay goes in （） after the Chinese or into the glossary")
ZH_NUMBERED = re.compile(r"^\s*(?:[一二三四五六七八九十]+[、.．]|第[一二三四五六七八九十百0-9]+[章节部分篇]|"
                         r"(?:[IVXL]+|[0-9]+(?:\.[0-9]+)*)(?:[.、．]|\s))")


def residue_words(zh: str, allow: set) -> list:
    """Lowercase English words left in a translation, outside brackets, quotes, citations and inline maths."""
    bare = RESIDUE_SKIP.sub(" ", zh)
    return sorted({w for w in RESIDUE_WORD.findall(bare) if w not in allow and w not in RESIDUE_OK})


def check_zh(zh: str, en: str, where: str, errors: list, warnings: list, allow: set = frozenset()):
    if not zh or not zh.strip():
        errors.append(f"{where}: missing Chinese translation (zh)")
        return
    if re.search(r"<[a-zA-Z/]|\*\*|^#", zh):
        errors.append(f"{where}: zh must be plain text (no HTML/Markdown)")
    if MISSING in zh:
        errors.append(f"{where}: zh still contains {MISSING}")
    words = len(EN_WORD.findall(en))
    han = len(CJK.findall(zh))
    if words >= 25:
        ratio = han / words
        if ratio < 0.9:
            warnings.append(f"{where}: translation looks short ({han} 汉字 for {words} English words) - something omitted?")
        elif ratio > 3.2:
            warnings.append(f"{where}: translation looks long ({han} 汉字 for {words} English words) - padded?")
    if re.search(r"(?:\b[A-Za-z]{2,}\b[ ,;]+){9,}", zh):
        warnings.append(f"{where}: zh contains a long untranslated English run")
    stray = residue_words(zh, allow)
    if stray:
        warnings.append(f"{where}: zh keeps English words untranslated ({', '.join(stray[:8])}) - {RESIDUE_FIX}")


def check_note(note, where, stages, errors, warnings):
    if not isinstance(note, dict):
        errors.append(f"{where}: note missing")
        return
    for k in ("func", "role"):
        if not str(note.get(k, "")).strip():
            errors.append(f"{where}: note.{k} is empty")
    if not (str(note.get("craft", "")).strip() or str(note.get("gap", "")).strip()):
        errors.append(f"{where}: note needs craft (技巧) and/or gap (漏洞)")
    if note.get("stage") not in stages:
        errors.append(f"{where}: note.stage must be one of {', '.join(stages)} (got {note.get('stage')!r})")
    if len(str(note.get("func", ""))) > 16:
        warnings.append(f"{where}: note.func should be a short label (≤16 chars), put explanation in role/craft")


# ------------------------------------------------------------------ build
def build(work: Path, out: Path | None, allow_partial: bool, sections_spec: str | None, check_only: bool):
    errors, warnings = [], []
    profiles = json.loads((ASSETS / "profiles.json").read_text(encoding="utf-8"))
    colors, stages = profiles["colors"], profiles["stages"]

    src = load_json(work / "source.json", errors)
    meta = load_json(work / "annot" / "meta.json", errors, required=not allow_partial) or {}
    if src is None:
        return errors, warnings, None
    prof_key = meta.get("profile")
    if prof_key not in profiles["profiles"]:
        (warnings if allow_partial else errors).append(
            f"meta.json: profile must be one of {', '.join(profiles['profiles'])} (got {prof_key!r})")
        prof_key = prof_key if prof_key in profiles["profiles"] else "argument"
    prof = profiles["profiles"][prof_key]

    all_sections = src["sections"]
    sections = select_sections(all_sections, sections_spec)
    partial_view = len(sections) != len(all_sections)
    item_ids = {it.get("id") for s in all_sections for it in s["items"] if it.get("id")}

    # glossary tooltips for red highlights
    tips = {}
    for g in meta.get("glossary", []) or []:
        tip = g.get("zh", "")
        if g.get("def"):
            tip = f"{tip}\n{g['def']}" if tip else g["def"]
        for t in [g.get("term", "")] + list(g.get("aliases", []) or []):
            if t:
                tips[t.lower().strip()] = tip
    allow = {w for t in tips for w in re.findall(r"[a-z]+", t)}

    color_use = Counter()
    no_hl = 0
    n_paras = 0
    seen_craft = Counter()
    body_parts, nav = [], []
    first_l1 = None

    for sec in sections:
        sid = sec["id"]
        ann = load_json(work / "annot" / f"{sid}.json", errors, required=not allow_partial) or {}
        ann_items = ann.get("items", {}) or {}
        unknown = set(ann_items) - {it.get("id") for it in sec["items"]}
        for u in sorted(unknown):
            errors.append(f"annot/{sid}.json: item {u!r} does not exist in section {sid} of source.json")

        level = sec.get("level", 1)
        title = sec.get("title", "")
        title_zh = ann.get("title_zh", "")
        if level == 1:
            m = SEC_NUM.match(title)
            numbered_zh = bool(title_zh and ZH_NUMBERED.match(title_zh))
            label = (m.group(1) + " " if m and not numbered_zh else "") + (title_zh or title)
            label = label if len(label) <= 26 else label[:25] + "…"
            nav.append(f'<a href="#{esc(sid)}">{esc(label)}</a>')
            first_l1 = first_l1 or sid
        elif not title_zh and not allow_partial:
            warnings.append(f"annot/{sid}.json: title_zh missing")
        spy = ' data-spy=""' if level == 1 else ""
        head = (f'<section class="sec" id="{esc(sid)}"{spy}>\n<div class="sec-head l{level}">'
                f'<h2>{esc(title)}</h2>' + (f'<span class="h-zh">{esc(title_zh)}</span>' if title_zh else "") + "</div>")
        if ann.get("summary"):
            stray = residue_words(ann["summary"], allow)
            if stray:
                warnings.append(f"annot/{sid}.json: summary keeps English words untranslated "
                                f"({', '.join(stray[:8])}) - {RESIDUE_FIX}")
            head +=f'\n<p class="sec-summary">{esc(ann["summary"])}</p>'
        rows = [head]
        if sec["items"] and all(it.get("kind") == "keywords" for it in sec["items"]):
            warnings.append(f"{sid}: section holds only keywords - move them into the abstract's section "
                            "and delete this one (step 2), before annotating it")

        for it in sec["items"]:
            iid = it.get("id") or ""
            kind = it["kind"]
            a = ann_items.get(iid)
            where = f"{sid}/{iid}"
            if a is None and kind in ("para", "keywords", "figure", "table") and not allow_partial:
                errors.append(f"{where}: no annotation entry in annot/{sid}.json")
            a = a or {}
            note = a.get("note")
            left = ""
            if kind in ("para", "keywords"):
                text = it.get("text", "")
                if MISSING in text:
                    errors.append(f"{where}: source text still contains {MISSING} - fix it from the page image")
                spans = find_spans(text, a.get("hl", []) or [], where, errors)
                for s in spans:
                    if s[2] not in colors:
                        errors.append(f"{where}: unknown colour {s[2]!r} (use {', '.join(colors)})")
                if kind == "para":
                    n_paras += 1
                    if a:
                        if not spans:
                            no_hl += 1
                        if len(spans) > 5:
                            warnings.append(f"{where}: {len(spans)} highlights - keep to the 2-4 that carry the argument")
                        cover = sum(b - x for x, b, *_ in spans) / max(1, len(text))
                        if cover > 0.4:
                            warnings.append(f"{where}: {cover:.0%} of the paragraph highlighted - too much, select")
                for s in spans:
                    color_use[s[2]] += 1
                en_cls = "en kw" if kind == "keywords" else "en"
                runin = it.get("runin") or ""
                if runin and not text.startswith(runin):
                    errors.append(f"{where}: runin {runin!r} must be the exact start of text")
                    runin = ""
                left = f'<p class="{en_cls}">{render_en(text, spans, tips, len(runin))}</p>'
                if a:
                    check_zh(a.get("zh", ""), text, where, errors, warnings, allow)
                if a.get("zh"):
                    left += f'\n<hr class="split"><p class="zh">{esc(a["zh"])}</p>'
                if kind == "para" and a and not allow_partial or (kind == "para" and note is not None):
                    check_note(note, where, stages, errors, warnings)
                dominant = Counter()
                for x, b, color, _ in spans:
                    dominant[color] += b - x
                card_color = dominant.most_common(1)[0][0] if dominant else ""
            elif kind in ("figure", "table"):
                cap = it.get("caption", "")
                if MISSING in cap:
                    errors.append(f"{where}: caption still contains {MISSING}")
                m = CAP_PREFIX.match(cap)
                cap_html = (f"<b>{esc(m.group(1))}</b> {esc(cap[m.end():])}" if m else esc(cap))
                img_html = ""
                img = it.get("image")
                if img and (work / img).exists():
                    uri = embed_image(work / img, warnings)
                    img_html = f'<img src="{uri}" alt="{esc(cap[:120])}" loading="lazy">'
                elif kind == "figure" or not a.get("table"):
                    errors.append(f"{where}: image file missing ({img})")
                tbl = a.get("table")
                if tbl:
                    thead = "".join(f"<th>{esc(c)}</th>" for c in tbl.get("header", []))
                    tbody = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in tbl.get("rows", []))
                    media = (f'<div class="tablewrap"><table class="data"><thead><tr>{thead}</tr></thead>'
                             f"<tbody>{tbody}</tbody></table></div>")
                    if img_html:
                        media += f'<details class="orig"><summary>原表截图</summary>{img_html}</details>'
                else:
                    media = img_html
                zh = a.get("zh", "")
                if a and not zh:
                    errors.append(f"{where}: caption translation (zh) missing")
                caption = (f'<figcaption><p class="cap-en">{cap_html}</p>'
                           + (f'<hr class="split"><p class="zh">{esc(zh)}</p>' if zh else "") + "</figcaption>")
                # tables are captioned above (IEEE/APA convention), figures below
                left = f'<figure>{caption}{media}</figure>' if kind == "table" else f'<figure>{media}{caption}</figure>'
                card_color = "blue" if prof_key != "argument" else ""
                if note is not None:
                    check_note(note, where, stages, errors, warnings)
            elif kind == "equation":
                latex = a.get("latex") or it.get("latex") or ""
                num = it.get("number", "")
                if not latex:
                    warnings.append(f"{where}: equation has no LaTeX - showing raw text")
                    left = f'<div class="eq"><span class="raw">{esc(it.get("raw", ""))}</span></div>'
                else:
                    tex = latex + (f" \\tag{{{num}}}" if num and "\\tag" not in latex else "")
                    left = f'<div class="eq" data-latex="{esc(tex)}"><span class="raw">{esc(tex)}</span></div>'
                if a.get("zh"):
                    left += f'<p class="zh">{esc(a["zh"])}</p>'
                card_color = "purple"
            else:
                continue

            if note:
                if note.get("craft"):
                    seen_craft[note["craft"].strip()] += 1
                stage = note.get("stage", "")
                dl = [f'<dt>逻辑角色</dt><dd>{esc(note.get("role", ""))}</dd>']
                if note.get("craft"):
                    dl.append(f'<dt>论证技巧</dt><dd>{esc(note["craft"])}</dd>')
                if note.get("gap"):
                    dl.append(f'<dt>潜在漏洞</dt><dd class="gap">{esc(note["gap"])}</dd>')
                stage_html = (f'<span class="stage {esc(stage)}">{esc(prof["stages"].get(stage, stage))}</span>'
                              if stage else "")
                right = (f'<aside class="note {esc(card_color)}"><div class="head"><span class="func">'
                         f'{esc(note.get("func", ""))}</span>{stage_html}</div><dl>{"".join(dl)}</dl></aside>')
            elif kind == "para" and not a:
                right = '<aside class="note pending">尚未批注</aside>'
            else:
                right = '<aside class="note" aria-hidden="true" style="visibility:hidden"></aside>'
            anchor = f'<a class="pid" href="#{esc(iid)}" title="链接到此段">{esc(iid)}</a>' if iid else ""
            rows.append(f'<div class="row" id="{esc(iid)}"><div class="src">{anchor}{left}</div>{right}</div>')
        rows.append("</section>")
        body_parts.append("\n".join(rows))

    # ---- document-wide checks
    if not partial_view and not allow_partial:
        for c in colors:
            if not color_use[c]:
                warnings.append(f"colour {c} ({prof['labels'][c]}) is never used - check the paper really has none")
        if n_paras and no_hl / n_paras > 0.35:
            warnings.append(f"{no_hl}/{n_paras} paragraphs have no highlight")
    for craft, n in seen_craft.items():
        if n > 1 and len(craft) > 6:
            warnings.append(f"same craft note repeated {n}x: {craft[:40]!r} - make each note specific")

    # ---- overview
    ov = meta.get("overview") or {}

    def refs_html(refs, where):
        out = []
        for r in refs or []:
            if r not in item_ids and r not in {s["id"] for s in all_sections}:
                errors.append(f"meta.json overview {where}: unknown ref {r!r}")
                continue
            out.append(f'<a href="#{esc(r)}">{esc(r)}</a>')
        return f'<div class="refs">{"".join(out)}</div>' if out else ""

    if ov:
        sk = ov.get("skeleton") or {}
        steps = []
        for st in stages:
            node = sk.get(st)
            if not node or not str(node.get("text", "")).strip():
                errors.append(f"meta.json overview.skeleton.{st} missing")
                node = {"text": "—"}
            steps.append(f'<div class="step {st}"><div class="label">{esc(prof["stages"][st])}</div>'
                         f'<div>{esc(node.get("text", ""))}</div>{refs_html(node.get("refs"), "skeleton." + st)}</div>')
        th = ov.get("thesis") or {}
        if not str(th.get("zh", "")).strip():
            errors.append("meta.json overview.thesis.zh missing")
        parts = [f'<section class="overview" id="overview" data-spy=""><h2>论证结构总览</h2>',
                 '<h3>全文逻辑骨架</h3>', f'<div class="flow">{"".join(steps)}</div>',
                 '<h3>作者核心主张（一句话）</h3>',
                 f'<div class="thesis">{esc(th.get("zh", ""))}'
                 + (f'<div class="en">{esc(th["en"])}</div>' if th.get("en") else "") + "</div>"]
        sv = []
        for key, cls, label in (("strongest", "strong", "▲ 论证最强处"), ("weakest", "weak", "▼ 论证最弱处")):
            node = ov.get(key) or {}
            if not str(node.get("text", "")).strip():
                errors.append(f"meta.json overview.{key} missing")
            sv.append(f'<div class="card {cls}"><div class="t">{label}</div><div>{esc(node.get("text", ""))}</div>'
                      f'{refs_html(node.get("refs"), key)}</div>')
        parts += ['<h3>最强处 vs 最弱处</h3>', f'<div class="versus">{"".join(sv)}</div>']
        claims = ov.get("claims") or []
        if claims:
            strength = {"strong": "强", "medium": "中", "weak": "弱"}
            trs = "".join(
                f'<tr><td>{esc(c.get("claim", ""))}</td><td>{esc(c.get("evidence", ""))}</td>'
                f'<td><span class="pill s-{esc(c.get("strength", "medium"))}">{strength.get(c.get("strength"), "中")}</span></td>'
                f'<td>{refs_html(c.get("refs"), "claims")}</td></tr>' for c in claims)
            parts += ['<h3>主张 — 证据对照</h3>',
                      f'<div class="tablewrap"><table class="grid"><thead><tr><th>主张</th><th>支撑证据</th><th>证据强度</th>'
                      f'<th>位置</th></tr></thead><tbody>{trs}</tbody></table></div>']
        gl = meta.get("glossary") or []
        if gl:
            trs = "".join(f'<tr><td class="term">{esc(g.get("term", ""))}</td><td>{esc(g.get("zh", ""))}</td>'
                          f'<td>{esc(g.get("def", ""))}</td></tr>' for g in gl)
            parts += ['<h3>术语表</h3>', f'<div class="tablewrap"><table class="grid"><thead><tr><th>术语</th><th>中文</th>'
                      f'<th>释义</th></tr></thead><tbody>{trs}</tbody></table></div>']
        parts.append("</section>")
        overview_html = "\n".join(parts)
        nav.append('<a class="overview" href="#overview">论证总览</a>')
    else:
        if not allow_partial:
            errors.append("meta.json: overview missing")
        overview_html = ""

    if check_only:
        return errors, warnings, None

    # ---- page chrome
    smeta = src.get("meta", {})
    title_en = smeta.get("title", "") or "Untitled"
    kicker = []
    if meta.get("course"):
        kicker.append(esc(meta["course"]))
    kicker.append(f'<span class="badge">{esc(prof["name"])}论文 · 五维批注</span>')
    byline = " · ".join(esc(x) for x in (meta.get("authors") or smeta.get("authors"),
                                          meta.get("venue") or smeta.get("venue"),
                                          meta.get("year") or smeta.get("year")) if x)
    if smeta.get("doi"):
        byline += (" · " if byline else "") + f'DOI <a href="https://doi.org/{esc(smeta["doi"])}">{esc(smeta["doi"])}</a>'
    legend = "".join(
        f'<button type="button" data-cat="{c}" aria-pressed="true" title="点击隐藏/显示这一类高亮">'
        f'<span class="sw" style="background:var(--{c}-bg);box-shadow:inset 0 -3px 0 var(--{c})"></span>'
        f'{esc(prof["labels"][c])}</button>' for c in colors)
    footer = ("原文版权归原作者与出版方所有。本页为个人学习用的批注与译文，请勿公开传播。"
              + (" · 仅预览部分章节" if partial_view else ""))
    tpl = (ASSETS / "template.html").read_text(encoding="utf-8")
    page = (tpl.replace("%%DOC_TITLE%%", esc((meta.get("title_zh") or title_en)[:80]) + " · 批注精读")
            .replace("%%KICKER%%", " ".join(kicker))
            .replace("%%TITLE_EN%%", esc(title_en))
            .replace("%%TITLE_ZH%%", f'<div class="title-zh">{esc(meta["title_zh"])}</div>' if meta.get("title_zh") else "")
            .replace("%%BYLINE%%", byline)
            .replace("%%LEGEND%%", legend)
            .replace("%%SECNAV%%", "".join(nav))
            .replace("%%BODY%%", "\n".join(body_parts))
            .replace("%%OVERVIEW%%", overview_html)
            .replace("%%FOOTER%%", footer))
    if out is None:
        slug = re.sub(r"[^A-Za-z0-9]+", "-", title_en).strip("-")[:50].strip("-") or "paper"
        out = work.parent / f"{slug}.annotated.html"
    if not errors or allow_partial:
        out.write_text(page, encoding="utf-8")
    marker = work / "built.json"
    if not errors and not allow_partial and not sections_spec:
        # a full, error-free build: organize_papers.py uses this to file the paper under done/
        marker.write_text(json.dumps({"html": out.name, "built_at": datetime.now().isoformat(timespec="seconds")},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
    elif allow_partial and marker.exists() and json.loads(marker.read_text(encoding="utf-8")).get("html") == out.name:
        marker.unlink()   # the preview just overwrote the finished build
    return errors, warnings, out


BATCH_WORDS = 1800   # one annotation batch ≈ what fits comfortably in one working pass
BATCH_ITEMS = 12


def status(work: Path) -> int:
    """Print progress and the single next action. Lets an agent resume after a context reset."""
    src = json.loads((work / "source.json").read_text(encoding="utf-8"))
    annot = work / "annot"
    meta_p = annot / "meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}

    rows, total_items, total_done = [], 0, 0
    for sec in src["sections"]:
        sid = sec["id"]
        p = annot / f"{sid}.json"
        ann = json.loads(p.read_text(encoding="utf-8")).get("items", {}) if p.exists() else {}
        need = [it for it in sec["items"] if it["kind"] in ("para", "keywords", "figure", "table")]
        done = 0
        for it in need:
            a = ann.get(it.get("id"), {}) or {}
            ok = bool(a.get("zh"))
            if it["kind"] == "para":
                ok = ok and bool(a.get("note"))
            done += ok
        words = sum(len(EN_WORD.findall(it.get("text", "") or it.get("caption", ""))) for it in sec["items"])
        rows.append(dict(id=sid, level=sec.get("level", 1), title=sec.get("title", ""),
                         need=len(need), done=done, words=words))
        total_items += len(need)
        total_done += done

    # greedy batches over consecutive sections; a level-1 heading may start a new batch
    batches, cur, cw, ci = [], [], 0, 0
    for r in rows:
        if cur and (cw + r["words"] > BATCH_WORDS or ci + r["need"] > BATCH_ITEMS):
            batches.append(cur)
            cur, cw, ci = [], 0, 0
        cur.append(r)
        cw += r["words"]
        ci += r["need"]
    if cur:
        batches.append(cur)

    missing = sum((it.get("text", "") + it.get("caption", "")).count(MISSING)
                  for s in src["sections"] for it in s["items"])
    no_latex = sum(1 for s in src["sections"] for it in s["items"] if it["kind"] == "equation" and not it.get("latex"))

    print(f"paper: {src.get('meta', {}).get('title', '')}")
    print(f"proofread: {'yes' if src.get('proofread') else 'NO'}   ⟨?⟩ left: {missing}   equations without latex in source.json: {no_latex} (may instead go in annot)")
    print(f"meta.json: {'profile=' + str(meta.get('profile')) if meta else 'MISSING'}"
          f"   overview final: {'yes' if meta.get('overview_final') else 'no'}")
    print(f"annotated: {total_done}/{total_items} items\n")
    for k, b in enumerate(batches, 1):
        n, d = sum(r["need"] for r in b), sum(r["done"] for r in b)
        mark = "done" if d == n else ("partial" if d else "todo")
        print(f"batch {k} [{mark}] {b[0]['id']}-{b[-1]['id']}  {d}/{n} items, {sum(r['words'] for r in b)} words")
        for r in b:
            print(f"    {r['id']:>4} {'  ' * (r['level'] - 1)}{r['title'][:60]}  ({r['done']}/{r['need']})")

    if not src.get("proofread") or missing:
        nxt = 'proofread source.json against pages/*.png (SKILL.md step 2), then set "proofread": true at its top level'
    elif not meta.get("profile"):
        nxt = "read the whole paper, write annot/meta.json with profile, glossary and draft overview (step 3)"
    elif total_done < total_items:
        b = next(b for b in batches if sum(r["done"] for r in b) < sum(r["need"] for r in b))
        ids = [r["id"] for r in b if r["done"] < r["need"]]
        nxt = f"annotate {', '.join(ids)} (step 4), then run --check"
    elif not meta.get("overview_final"):
        nxt = 'revise overview in meta.json (step 5), then set "overview_final": true'
    else:
        nxt = "build the final HTML and clear all errors (step 6)"
    print(f"\nNEXT: {nxt}")
    return 0


def dump(work: Path, spec: str | None) -> int:
    """Print the proofread text of some sections with item ids - the input for one annotation batch."""
    src = json.loads((work / "source.json").read_text(encoding="utf-8"))
    for sec in select_sections(src["sections"], spec):
        print(f"\n{'#' * (sec.get('level', 1) + 1)} [{sec['id']}] {sec.get('title', '')}\n")
        for it in sec["items"]:
            body = it.get("text") or it.get("caption") or ""
            extra = f"  latex: {it['latex']}" if it.get("latex") else ""
            print(f"[{it.get('id', '')}] ({it['kind']}) {body}{extra}\n")
    return 0


def main():
    argv = sys.argv[1:]
    if "--status" in argv or "--dump" in argv:
        sys.stdout.reconfigure(encoding="utf-8")
        if "--status" in argv:
            sys.exit(status(Path(argv[0])))
        i = argv.index("--dump")
        spec = argv[i + 1] if i + 1 < len(argv) else None
        sys.exit(dump(Path(argv[0]), spec))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--allow-partial", action="store_true")
    ap.add_argument("--sections")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    errors, warnings, out = build(a.work, a.out, a.allow_partial, a.sections, a.check)
    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    if out and (not errors or a.allow_partial):
        size = out.stat().st_size / 1024
        print(f"wrote {out} ({size:.0f} KB)")
    elif not a.check:
        print("nothing written - fix the errors above (or use --allow-partial for a preview)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
