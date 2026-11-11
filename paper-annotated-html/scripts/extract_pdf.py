#!/usr/bin/env python3
"""Extract an academic PDF into an editable source.json draft.

The output is a *draft*: paragraph boundaries, headings, symbols and equations
must be proofread against the page images before annotation starts.

Usage:
    python extract_pdf.py paper.pdf [--out WORK_DIR] [--skip-pages 1,2] [--dpi 110]
    python extract_pdf.py crop paper.pdf --page 4 --bbox x0,y0,x1,y1 --save WORK/figures/F2.png [--px]
        re-crop one figure/table; bbox in PDF points (as in source.json), or with --px in
        pixels of pages/page-NN.png (rendered at --dpi, default 110)

Writes into WORK_DIR (default: <pdf_dir>/<slug>_work/):
    source.json        sections -> items (para / figure / table / equation)
    source.md          human-readable preview with item ids
    pages/page-NN.png  page renders for proofreading
    figures/*.png      cropped figures and tables (check every crop!)
    extract_report.txt what was dropped, suspicious glyphs, warnings

Requires PyMuPDF (pip install pymupdf).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    sys.exit("PyMuPDF is required: pip install pymupdf")

MISSING = "⟨?⟩"  # marker for glyphs that have no usable unicode in the text layer
LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
COVER_HINTS = [
    "citation for published version", "link to publication", "general rights",
    "take down policy", "document license", "downloaded from", "this is a pdf file of an article",
    "terms of use", "document version",
]
CAPTION_RE = re.compile(r"^(Fig\.|Figure|Fig|TABLE|Table|Scheme|Chart)\s*([0-9]+|[IVXL]+)\s*[.:|]?", re.I)
REF_HEAD_RE = re.compile(r"^(references|bibliography|works cited|literature cited|参考文献)\s*$", re.I)
NAMED_HEAD_RE = re.compile(
    r"^(abstract|keywords|index terms|introduction|conclusions?|discussion|acknowledg(e)?ments?|appendix(es)?|"
    r"related work|background|methods?|results|materials and methods|limitations|future work)\s*$", re.I)
EQNUM_RE = re.compile(r"\((\d+[a-z]?)\)\s*$")


def clean_text(s: str) -> str:
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return s.replace("­", "")  # soft hyphen


def span_text(span) -> str:
    out = []
    for ch in span["chars"]:
        c = ch["c"]
        o = ord(c)
        if c in "\t\n\r":
            out.append(" ")
        elif o < 0x20 or o == 0xFFFD or 0xE000 <= o <= 0xF8FF:
            out.append(MISSING)
        else:
            out.append(c)
    return clean_text("".join(out))


class Line:
    __slots__ = ("page", "x0", "y0", "x1", "y1", "text", "size", "bold", "italic", "font", "col", "kind")

    def __init__(self, page, bbox, text, size, bold, italic, font):
        self.page = page
        self.x0, self.y0, self.x1, self.y1 = bbox
        self.text, self.size, self.bold, self.italic, self.font = text, size, bold, italic, font
        self.col = 0
        self.kind = "body"

    def __repr__(self):
        return f"<p{self.page} {self.kind} {self.x0:.0f},{self.y0:.0f} {self.size:.1f} {self.text[:40]!r}>"


def page_lines(page, pno, force_cols=None):
    """Visual lines per column.

    Spans are first assigned to a side (left column / right column / full width),
    then spans on one side that overlap vertically become one line. Merging never
    crosses the column gutter, which is what interleaves columns in naive extraction.
    Small caps ("I. I" + "NTRODUCTION") and justified words land in the same line.
    """
    W = page.rect.width
    mid = W / 2
    spans = []
    for b in page.get_text("rawdict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            if l["dir"][0] < 0.9:  # rotated text (axis labels, sidebars)
                continue
            for s in l["spans"]:
                t = span_text(s)
                if t.strip():
                    spans.append((list(s["bbox"]), t, s["size"], s["flags"], s["font"]))
    left_chars = sum(len(t) for bb, t, *_ in spans if bb[2] < mid + 8)
    right_chars = sum(len(t) for bb, t, *_ in spans if bb[0] > mid - 8)
    total = max(1, sum(len(t) for _, t, *_ in spans))
    # a real gutter: few text rows have anything crossing the page middle
    # (single-column justified text often comes as one span per word, so char counts alone mislead)
    row_keys = {round(bb[3] / 3) for bb, *_ in spans}
    cross = {round(bb[3] / 3) for bb, *_ in spans if bb[0] < mid - 3 and bb[2] > mid + 3}
    two_col = (left_chars > 0.25 * total and right_chars > 0.25 * total
               and len(cross) < 0.4 * max(1, len(row_keys)))
    if force_cols is False:
        two_col = False

    def side(bb):
        if not two_col:
            return 0
        if bb[2] < mid + 8:
            return 1
        if bb[0] > mid - 8:
            return 2
        return 0

    sizes = sorted(s[2] for s in spans)
    median = sizes[len(sizes) // 2] if sizes else 10
    dropcaps = [s for s in spans if len(s[1].strip()) <= 2 and s[2] > 1.8 * median and s[1].strip().isalpha()]
    spans = [s for s in spans if s not in dropcaps]

    rows = {0: [], 1: [], 2: []}
    for sp in sorted(spans, key=lambda s: ((s[0][1] + s[0][3]) / 2, s[0][0])):
        bb = sp[0]
        sd = side(bb)
        cy = (bb[1] + bb[3]) / 2
        for row in reversed(rows[sd][-4:]):
            if row["y0"] - 1 <= cy <= row["y1"] + 1 or abs(row["base"] - bb[3]) < 1.5:
                row["spans"].append(sp)
                row["y0"], row["y1"] = min(row["y0"], bb[1]), max(row["y1"], bb[3])
                break
        else:
            rows[sd].append({"y0": bb[1], "y1": bb[3], "base": bb[3], "spans": [sp]})

    lines = []
    for sd, rs in rows.items():
        for row in rs:
            sp = sorted(row["spans"], key=lambda s: s[0][0])
            # split a row where the horizontal gap is far larger than word spacing
            segs, cur = [], [sp[0]]
            for a, b in zip(sp, sp[1:]):
                if b[0][0] - a[0][2] > 3.2 * max(a[2], b[2]):
                    segs.append(cur)
                    cur = []
                cur.append(b)
            segs.append(cur)
            for seg in segs:
                text = ""
                for i, s in enumerate(seg):
                    if i:
                        gap = s[0][0] - seg[i - 1][0][2]
                        if gap > 0.15 * s[2] and not text.endswith(" ") and not s[1].startswith(" "):
                            text += " "
                    text += s[1]
                dom = max(seg, key=lambda s: len(s[1].strip()))
                # small caps headings: the capital letters carry the real size
                size = max([s[2] for s in seg if re.search(r"[A-Za-z]", s[1])] or [dom[2]])
                bbox = [min(s[0][0] for s in seg), min(s[0][1] for s in seg),
                        max(s[0][2] for s in seg), max(s[0][3] for s in seg)]
                font, flags = dom[4], dom[3]
                bold = bool(flags & 16) or "bold" in font.lower() or "medi" in font.lower()
                italic = bool(flags & 2) or "italic" in font.lower()
                ln = Line(pno, bbox, re.sub(r"\s+", " ", text).strip(), size, bold, italic, font)
                ln.col = sd
                if ln.text:
                    lines.append(ln)
    # re-join a full-width segment with neighbours on the same baseline (author lines, titles)
    changed = True
    while changed:
        changed = False
        for a in lines:
            for b in lines:
                if a is b or (a.col != 0 and b.col != 0):
                    continue
                gap = b.x0 - a.x1
                if abs(a.y1 - b.y1) < 1.5 and -1 < gap < 0.9 * max(a.size, b.size):
                    a.text = a.text + ("" if gap < 0.15 * a.size else " ") + b.text
                    a.x1, a.y0, a.y1, a.col = b.x1, min(a.y0, b.y0), max(a.y1, b.y1), 0
                    lines.remove(b)
                    changed = True
                    break
            if changed:
                break
    for s in dropcaps:
        ln = Line(pno, list(s[0]), s[1].strip(), s[2], False, False, s[4])
        ln.col = side(s[0])
        ln.kind = "dropcap"
        lines.append(ln)
    return lines, two_col


def graphic_rects(page):
    """Rectangles of images and vector drawings, clustered into figure-sized regions."""
    rects = []
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"])
        if r.width > 20 and r.height > 20:
            rects.append(r)
    try:
        for dr in page.get_drawings():
            r = fitz.Rect(dr["rect"])
            if r.width < 1 and r.height < 1:
                continue
            rects.append(r)
    except Exception:
        pass
    # cluster
    clusters = []
    for r in rects:
        r = fitz.Rect(r.x0 - 4, r.y0 - 4, r.x1 + 4, r.y1 + 4)
        merged = True
        while merged:
            merged = False
            for c in clusters:
                if c.intersects(r):
                    r |= c
                    clusters.remove(c)
                    merged = True
                    break
        clusters.append(r)
    return [c for c in clusters if c.width * c.height > 4000 and c.height > 25]


def is_cover_page(text: str) -> bool:
    low = text.lower()
    return sum(h in low for h in COVER_HINTS) >= 2


def reading_order(lines, width, two_col):
    """Bands split by wide full-width lines; inside a band: left column, then right column.

    Narrow lines that merely straddle the gutter (figure labels) are assigned to the
    column holding their centre so they cannot split a band.
    """
    mid = width / 2
    if not two_col:
        return sorted(lines, key=lambda l: (l.y0, l.x0))
    for l in lines:
        if l.col == 0 and not (l.kind in ("body", "caption", "title") and l.x1 - l.x0 > width * 0.5):
            l.col = 1 if (l.x0 + l.x1) / 2 < mid else 2
    lines = sorted(lines, key=lambda l: (l.y0, l.x0))
    out, band = [], []

    def flush():
        band.sort(key=lambda l: (l.col, l.y0, l.x0))
        out.extend(band)
        band.clear()

    for l in lines:
        if l.col == 0:
            flush()
            out.append(l)
        else:
            band.append(l)
    flush()
    return out


def heading_level(l: Line, body_size: float):
    t = l.text
    if len(t) > 110 or t.endswith((",", ";")):
        return None
    styled = l.bold or l.italic or l.size > body_size * 1.08 or (t.isupper() and len(t) > 3)
    if re.match(r"^[IVXL]+\.?\s+[A-Z][A-Z0-9 ,:;&/\-–()']+$", t) and styled | t.isupper():
        return 1
    if re.match(r"^\d+\.?\s+[A-Z]", t) and (l.bold or l.size > body_size * 1.08) and not t.endswith("."):
        return 1
    if re.match(r"^\d+\.\d+\.?\s+\S", t) and (l.bold or l.italic):
        return 2
    if re.match(r"^\d+\.\d+\.\d+\.?\s+\S", t) and (l.bold or l.italic):
        return 3
    if re.match(r"^[A-Z]\.\s+[A-Z][^.]{1,80}$", t) and l.italic:
        return 2
    if (NAMED_HEAD_RE.match(t) or REF_HEAD_RE.match(t)) and styled:
        return 1
    return None


def classify(lines, body_size, page_h, repeated):
    for l in lines:
        if l.kind == "dropcap":
            continue
        t = l.text
        norm = re.sub(r"\d+", "#", t)
        top = l.y1 < page_h * 0.075
        bottom = l.y0 > page_h * 0.925
        if (top or bottom) and (norm in repeated or re.fullmatch(r"[#\s\-–|/]*", norm) or l.size < body_size * 0.9):
            l.kind = "header"
        elif CAPTION_RE.match(t) and (l.size < body_size * 0.97 or (l.bold and l.size <= body_size * 1.01)):
            # same-size, non-bold "Figure 2. To provide..." is a body sentence, not a caption
            l.kind = "caption"
        elif len(t) <= 2 and l.size > body_size * 1.8:
            l.kind = "dropcap"
        elif l.size < body_size * 0.86:
            l.kind = "small"
        else:
            l.kind = "body"


def join_lines(prev: str, nxt: str) -> str:
    if not prev:
        return nxt
    if prev.endswith("-") and len(prev) > 1 and prev[-2].isalpha():
        if nxt[:1].islower():
            return prev[:-1] + nxt  # de-hyphenate "con-\nnection"
        return prev + nxt  # keep compound hyphen "20-\nkV"
    if prev.endswith(("—", "–", "/")):
        return prev + nxt
    return prev + " " + nxt


def extract(pdf: Path, out: Path, skip_pages: set[int], dpi: int):
    doc = fitz.open(pdf)
    report = []
    out.mkdir(parents=True, exist_ok=True)
    (out / "pages").mkdir(exist_ok=True)
    (out / "figures").mkdir(exist_ok=True)

    pages = []
    for pno, page in enumerate(doc):
        if (pno + 1) in skip_pages:
            report.append(f"page {pno + 1}: skipped by --skip-pages")
            continue
        if pno < 2 and is_cover_page(page.get_text()):
            report.append(f"page {pno + 1}: looks like a repository cover page -> skipped")
            continue
        ls, two = page_lines(page, pno + 1)
        pages.append((pno, page, ls, two))

    # layout is a property of the document: a single-column paper whose heatmap page
    # happens to look two-column must not be split down the middle
    n_two = sum(1 for *_, two in pages if two)
    if pages and n_two < 0.5 * len(pages):
        if n_two:
            report.append(f"layout: single-column document ({n_two}/{len(pages)} pages looked two-column, forced single)")
        pages = [(pno, page, *page_lines(page, pno + 1, force_cols=False)) for pno, page, _, _ in pages]
    else:
        report.append(f"layout: two-column document ({n_two}/{len(pages)} pages)")

    all_lines = [l for _, _, ls, _ in pages for l in ls]
    if not all_lines:
        sys.exit("No text layer found - this PDF is probably scanned. Run OCR first (e.g. ocrmypdf).")
    size_chars = Counter()
    for l in all_lines:
        size_chars[round(l.size, 1)] += len(l.text)
    body_size = size_chars.most_common(1)[0][0]

    # header/footer candidates: normalised text repeated on >= 3 pages near the margins
    edge = Counter()
    for pno, page, ls, _ in pages:
        h = page.rect.height
        seen = set()
        for l in ls:
            if l.y1 < h * 0.075 or l.y0 > h * 0.925:
                seen.add(re.sub(r"\d+", "#", l.text))
        edge.update(seen)
    repeated = {k for k, v in edge.items() if v >= 3}

    title = None
    title_candidates = []
    for pno, page, ls, _ in pages[:1]:
        big = max((l for l in ls if l.kind != "dropcap"), key=lambda l: l.size)
        title_candidates = [l for l in ls if abs(l.size - big.size) < 0.6 and l.y0 < page.rect.height * 0.45]
        title = " ".join(l.text for l in sorted(title_candidates, key=lambda l: (round(l.y0 / 4), l.x0)))

    ordered = []  # (line, page_obj)
    figures = []
    page_meta = {}
    for pno, page, ls, two in pages:
        classify(ls, body_size, page.rect.height, repeated)
        for l in title_candidates:
            l.kind = "title"
        gfx = graphic_rects(page)
        # text inside figure graphics = figure labels, not body text
        for l in ls:
            if l.kind == "body" and not heading_level(l, body_size):
                lr = fitz.Rect(l.x0, l.y0, l.x1, l.y1)
                for g in gfx:
                    if g.contains(lr) and g.height > 40 and (g.width < page.rect.width * 0.9 or g.height < page.rect.height * 0.8):
                        l.kind = "figtext"
                        break
        page_meta[pno] = (page, two, gfx, ls)
        pix = page.get_pixmap(dpi=dpi)
        pix.save(out / "pages" / f"page-{pno + 1:02d}.png")
        ordered.extend(reading_order(ls, page.rect.width, two))

    # ---- figure/table crops -------------------------------------------------
    # Crops exclude the caption (captions are rendered and translated as text).
    # They are guesses: every crop must be checked, and fixed with the `crop` subcommand.
    fig_index = {}
    for pno, (page, two, gfx, ls) in page_meta.items():
        W, H = page.rect.width, page.rect.height

        def col_span(l):
            if not two:
                return (30, W - 30)
            cx = (l.x0 + l.x1) / 2
            if l.col == 0 and ((l.x1 - l.x0) > W * 0.45 or abs(cx - W / 2) < W * 0.08):
                return (30, W - 30)
            return (30, W / 2 + 4) if cx < W / 2 else (W / 2 - 4, W - 30)

        def hov(a0, a1, b0, b1):  # real horizontal overlap, not just touching at the gutter
            return min(a1, b1) - max(a0, b0) > 20

        def overlaps(l, span):
            return hov(l.x0, l.x1, span[0], span[1])

        def prose(l, span):
            return l.kind == "body" and ((l.x1 - l.x0) >= 0.8 * (span[1] - span[0] - 12)
                                         or bool(heading_level(l, body_size)))

        drawn = [d["rect"] for d in page.get_drawings() if d["rect"].width > 2 or d["rect"].height > 2]

        # 1. caption blocks (first line + continuation lines)
        blocks = []
        for cap in sorted((l for l in ls if l.kind == "caption"), key=lambda l: l.y0):
            m = CAPTION_RE.match(cap.text)
            is_table = m.group(1).lower().startswith("tab")
            fid = ("T" if is_table else "F") + m.group(2)
            span = col_span(cap)

            def in_span(l):
                return l.x0 >= span[0] - 6 and l.x1 <= span[1] + 6

            bottom = cap.y1
            while True:
                cont = [l for l in ls if l.kind in ("small", "caption", "body") and l is not cap and in_span(l)
                        and 0 <= l.y0 - bottom < 0.6 * cap.size and abs(l.size - cap.size) < 0.6]
                if not cont:
                    break
                c = min(cont, key=lambda l: l.y0)
                cap.text += " " + c.text
                c.kind = "caption_cont"
                bottom = c.y1
            blocks.append({"cap": cap, "fid": fid, "table": is_table, "span": span, "top": cap.y0, "bottom": bottom})

        taken = []  # rects already claimed on this page (act as barriers)

        def save(blk, rect, where=""):
            fid, cap = blk["fid"], blk["cap"]
            if fid in fig_index:
                return
            if rect.height < 15 or rect.width < 30:
                report.append(f"{fid}: crop too small on page {pno + 1} - crop manually")
                return
            fname = f"{fid}.png"
            page.get_pixmap(dpi=200, clip=rect).save(out / "figures" / fname)
            fig_index[fid] = {
                "id": fid, "kind": "table" if blk["table"] else "figure", "page": pno + 1,
                "bbox": [round(v, 1) for v in rect], "image": f"figures/{fname}",
                "caption": cap.text,
            }
            if where:
                fig_index[fid]["table_position"] = where
            taken.append(rect)
            # text inside the crop (table cells, figure labels) is part of the image, not body text
            for l in ls:
                if l.kind in ("body", "small") and rect.contains(fitz.Point((l.x0 + l.x1) / 2, (l.y0 + l.y1) / 2)):
                    l.kind = "figtext"
            cap.kind = "caption_done"
            cap.text = fid  # placeholder used for placement

        def limit_above(blk, barrier):
            span = blk["span"]
            ys = [l.y1 for l in ls if barrier(l, span) and overlaps(l, span) and l.y1 < blk["top"] - 2]
            ys += [o["bottom"] for o in blocks if o is not blk and o["bottom"] < blk["top"] - 2
                   and hov(*o["span"], *span)]
            ys += [r.y1 for r in taken if r.y1 < blk["top"] - 2 and hov(r.x0, r.x1, *span)]
            top = max(ys) if ys else H * 0.06
            # the short last line of a paragraph sits right under it: still prose
            while True:
                tail = [l for l in ls if l.kind == "body" and overlaps(l, span)
                        and 0 <= l.y0 - top < 0.6 * body_size and l.y1 < blk["top"] - 2]
                if not tail:
                    return top
                top = max(l.y1 for l in tail)

        def limit_below(blk, barrier):
            span = blk["span"]
            ys = [l.y0 for l in ls if barrier(l, span) and overlaps(l, span) and l.y0 > blk["bottom"] + 2
                  and l.kind != "caption_cont"]
            ys += [o["top"] for o in blocks if o is not blk and o["top"] > blk["bottom"] + 2
                   and hov(*o["span"], *span)]
            return min(ys) if ys else H * 0.93

        def table_extent(blk, lo, hi, upward):
            """Walk away from the caption over table rows and rules; stop at the first big gap."""
            span = blk["span"]
            elems = [(l.y0, l.y1) for l in ls if overlaps(l, span) and lo < l.y0 and l.y1 < hi
                     and l.kind not in ("header", "caption_cont", "caption")]
            elems += [(r.y0, r.y1) for r in drawn if hov(r.x0, r.x1, *span) and lo < r.y0 and r.y1 < hi]
            if not elems:
                return lo, hi
            gap_max = 1.8 * body_size
            if upward:
                edge = blk["top"]
                for y0, y1 in sorted(elems, key=lambda e: -e[1]):
                    if edge - y1 > gap_max:
                        break
                    edge = min(edge, y0)
                return edge - 2, blk["top"] - 1
            edge = blk["bottom"]
            for y0, y1 in sorted(elems, key=lambda e: e[0]):
                if y0 - edge > gap_max:
                    break
                edge = max(edge, y1)
            return blk["bottom"] + 1, edge + 2

        # 2. tables first: caption above the table (IEEE "TABLE I") or below it (many journals)
        for blk in (b for b in blocks if b["table"]):
            span = blk["span"]
            nxt = [l for l in ls if overlaps(l, span) and l.y0 > blk["bottom"] + 1
                   and l.kind not in ("header", "caption_cont")]
            first = min(nxt, key=lambda l: l.y0) if nxt else None
            table_above = first is None or (prose(first, span) and first.y0 - blk["bottom"] < 2.5 * body_size)
            if table_above:
                y0, y1 = table_extent(blk, limit_above(blk, prose), blk["top"], upward=True)
                save(blk, fitz.Rect(span[0], y0, span[1], y1), "above caption")
            else:
                y0, y1 = table_extent(blk, blk["bottom"], limit_below(blk, prose), upward=False)
                save(blk, fitz.Rect(span[0], y0, span[1], y1), "below caption")

        # 3. figures: the region above the caption, bounded by body text, other captions and tables
        for blk in (b for b in blocks if not b["table"]):
            span = blk["span"]
            top = limit_above(blk, lambda l, sp: l.kind == "body")
            region = [g for g in gfx if g.y1 <= blk["top"] + 6 and g.y0 >= top - 6 and hov(g.x0, g.x1, *span)]
            rect = fitz.Rect(span[0], top + 2, span[1], blk["top"] - 1)
            if region:
                r = region[0]
                for g in region[1:]:
                    r |= g
                rect = fitz.Rect(max(span[0], r.x0), max(top + 1, r.y0), min(span[1], r.x1), blk["top"] - 1)
            save(blk, rect)

    # ---- assemble sections ---------------------------------------------------
    sections = []
    cur = {"id": "S0", "title": "Front matter", "level": 1, "items": []}
    sections.append(cur)
    para = None
    prev_line = None
    in_refs = False
    refs_lines = 0
    dropped = Counter()
    front_text = []
    seen_heading = False
    pending_dropcap = ""
    col_left = {}

    def new_section(title, level):
        nonlocal cur, para
        para = None
        cur = {"id": f"S{len(sections)}", "title": title, "level": level, "items": []}
        sections.append(cur)

    def close_para():
        nonlocal para
        para = None

    # left margin per (page,col) to detect first-line indents
    for l in ordered:
        if l.kind == "body":
            key = (l.page, l.col)
            col_left[key] = min(col_left.get(key, 9e9), l.x0)
    pitches = []
    for a, b in zip(ordered, ordered[1:]):
        if a.kind == b.kind == "body" and a.page == b.page and a.col == b.col and 0 < b.y0 - a.y0 < body_size * 2.2:
            pitches.append(b.y0 - a.y0)
    pitch = statistics.median(pitches) if pitches else body_size * 1.2

    for l in ordered:
        if l.kind in ("header", "figtext", "caption_cont", "title"):
            dropped[l.kind] += 1
            continue
        if l.kind == "small":
            dropped["small"] += 1
            continue
        if l.kind == "dropcap":
            pending_dropcap = l.text
            continue
        if l.kind == "caption":  # caption we could not crop
            fid_m = CAPTION_RE.match(l.text)
            cur["items"].append({"kind": "figure", "id": None, "caption": l.text, "image": None,
                                 "note": "crop failed - crop manually"})
            continue
        if l.kind == "caption_done":
            if in_refs:
                continue
            cur["items"].append(dict(fig_index[l.text]))
            continue
        t = l.text
        lvl = heading_level(l, body_size)
        if lvl:
            if REF_HEAD_RE.match(t):
                in_refs = True
                close_para()
                continue
            if in_refs and lvl == 1 and re.match(r"^(appendix|[IVX]+\.?\s|\d+\s)", t, re.I):
                in_refs = False  # appendix after references
            if not in_refs:
                seen_heading = True
                if re.match(r"^abstract", t, re.I):
                    cur["title"] = "Abstract"
                    cur["items"] = []
                    close_para()
                else:
                    new_section(t, lvl)
                prev_line = l
                continue
        if in_refs:
            refs_lines += 1
            continue
        # two-line headings: "IV. HIGH REPETITION RATE OPERATION" + "AND FAST RECHARGING"
        if (prev_line is not None and not cur["items"] and cur["id"] != "S0" and t.isupper() and len(t) < 70
                and heading_level(prev_line, body_size) and abs(l.y0 - prev_line.y1) < body_size * 1.2):
            cur["title"] += " " + t
            prev_line = l
            continue
        if not seen_heading and cur["id"] == "S0":
            if re.match(r"^abstract\s*[—–:\-.]", t, re.I):
                seen_heading = True
                cur["title"] = "Abstract"
                t = re.sub(r"^abstract\s*[—–:\-.]\s*", "", t, flags=re.I)
            else:
                front_text.append(t)
                continue
        if pending_dropcap:
            t = pending_dropcap + t
            pending_dropcap = ""
        # equation line?
        left = col_left.get((l.page, l.col), l.x0)
        m = EQNUM_RE.search(t)
        if m and l.x0 > left + 12 and len(t) < 120:
            close_para()
            cur["items"].append({"kind": "equation", "number": m.group(1), "raw": t, "latex": ""})
            prev_line = l
            continue
        start_new = para is None
        if not start_new and prev_line is not None:
            same_flow = prev_line.page == l.page and prev_line.col == l.col
            if same_flow:
                gap = l.y0 - prev_line.y0
                if gap > pitch * 1.45:
                    start_new = True
                elif l.x0 > left + 6 and l.x0 - left < 30 and prev_line.x0 <= left + 3:
                    start_new = True
            else:
                # column/page change: continue only if paragraph looks unfinished or new line not indented
                if l.x0 > left + 6 and re.search(r"[.?!:\"”)]$", para["text"]):
                    start_new = True
        if start_new:
            para = {"kind": "para", "text": t, "page": l.page}
            cur["items"].append(para)
        else:
            para["text"] = join_lines(para["text"], t)
        prev_line = l

    # display equations come out as a "(n)" line plus short fragments: fold fragments into the equation
    for s in sections:
        items = s["items"]
        for i, it in enumerate(items):
            if it["kind"] != "equation":
                continue
            for j in (i - 1, i + 1):
                if 0 <= j < len(items) and items[j]["kind"] == "para" and len(items[j]["text"]) < 60:
                    it["raw"] = (items[j]["text"] + "  " + it["raw"]) if j < i else (it["raw"] + "  " + items[j]["text"])
                    items[j]["kind"] = "_absorbed"
        s["items"] = [it for it in items if it["kind"] != "_absorbed"]
    # keywords/index terms paragraphs -> flag them
    for s in sections:
        for it in s["items"]:
            if it["kind"] == "para" and re.match(r"^(index terms|keywords)\s*[—–:\-]", it["text"], re.I):
                it["kind"] = "keywords"
    # ids
    sections = [s for s in sections if s["items"] or s["level"] == 1]
    for si, s in enumerate(sections):
        s["id"] = f"S{si}"
        n = 0
        for it in s["items"]:
            if it["kind"] in ("figure", "table") and it.get("id"):
                continue
            n += 1
            it["id"] = f"{s['id']}.{'P' if it['kind'] == 'para' else it['kind'][0].upper()}{n}"

    missing = sum(it.get("text", "").count(MISSING) for s in sections for it in s["items"])
    src = {
        "meta": {
            "title": title or pdf.stem, "authors": "", "venue": "", "year": "", "doi": "",
            "pdf": pdf.name, "front_text": " | ".join(front_text)[:2000],
        },
        "sections": sections,
        "stats": {
            "body_font_size": body_size, "paragraphs": sum(1 for s in sections for it in s["items"] if it["kind"] == "para"),
            "figures": len(fig_index), "missing_glyphs": missing, "reference_lines_skipped": refs_lines,
        },
    }
    m = re.search(r"\b(10\.\d{4,9}/[^\s\"<>]+)", doc[0].get_text() + (doc[1].get_text() if len(doc) > 1 else ""))
    if m:
        src["meta"]["doi"] = m.group(1).rstrip(".")
    (out / "source.json").write_text(json.dumps(src, ensure_ascii=False, indent=1), encoding="utf-8")

    md = [f"# {src['meta']['title']}\n"]
    for s in sections:
        md.append(f"\n{'#' * (s['level'] + 1)} [{s['id']}] {s['title']}\n")
        for it in s["items"]:
            if it["kind"] in ("para", "keywords"):
                md.append(f"[{it['id']}] (p{it['page']}) {it['text']}\n")
            elif it["kind"] == "equation":
                md.append(f"[{it['id']}] EQUATION ({it['number']}): {it['raw']}\n")
            else:
                md.append(f"[{it.get('id')}] {it['kind'].upper()} -> {it.get('image')} :: {it.get('caption', '')}\n")
    (out / "source.md").write_text("\n".join(md), encoding="utf-8")

    report += [
        f"body font size: {body_size}",
        f"paragraphs: {src['stats']['paragraphs']}, figures/tables cropped: {len(fig_index)}",
        f"missing glyph markers {MISSING}: {missing}  (fix each one from the page image)",
        f"dropped lines: {dict(dropped)}  (small = footnotes/table cells/figure labels - check nothing important was lost)",
        f"reference lines skipped: {refs_lines}",
    ]
    for s in sections:
        for it in s["items"]:
            if it["kind"] == "para" and len(it["text"]) < 60:
                report.append(f"short paragraph {it['id']}: {it['text']!r} (heading? fragment?)")
            if it["kind"] == "para" and not re.search(r"[.?!:\"”)\]]$", it["text"]):
                report.append(f"unfinished paragraph {it['id']}: ...{it['text'][-50:]!r} (split across a figure/page?)")
    (out / "extract_report.txt").write_text("\n".join(report), encoding="utf-8")
    return src, report


def crop_main(argv):
    ap = argparse.ArgumentParser(prog="extract_pdf.py crop")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--page", type=int, required=True, help="1-based page number")
    ap.add_argument("--bbox", required=True, help="x0,y0,x1,y1")
    ap.add_argument("--save", type=Path, required=True)
    ap.add_argument("--px", action="store_true", help="bbox is in page-image pixels")
    ap.add_argument("--dpi", type=int, default=110, help="dpi of the page images (with --px)")
    a = ap.parse_args(argv)
    box = [float(v) for v in a.bbox.split(",")]
    if a.px:
        box = [v * 72 / a.dpi for v in box]
    page = fitz.open(a.pdf)[a.page - 1]
    rect = fitz.Rect(*box) & page.rect
    a.save.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=200, clip=rect).save(a.save)
    print(f"saved {a.save}  bbox(pt)={[round(v, 1) for v in rect]}  -> update this bbox in source.json")


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to GBK/cp1252
    if len(sys.argv) > 1 and sys.argv[1] == "crop":
        return crop_main(sys.argv[2:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--skip-pages", default="", help="1-based page numbers to ignore, e.g. 1,2")
    ap.add_argument("--dpi", type=int, default=110, help="page render resolution for proofreading")
    ap.add_argument("--force", action="store_true", help="overwrite an existing source.json (loses proofreading)")
    a = ap.parse_args()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", a.pdf.stem).strip("-")[:40].strip("-") or "paper"
    out = a.out or a.pdf.parent / f"{slug}_work"
    if (out / "source.json").exists() and not a.force:
        print(f"work dir already exists: {out}\n"
              f"resume instead:  python build_html.py \"{out}\" --status\n"
              f"(re-extract with --force only if you want to discard the proofread source.json)")
        sys.exit(2)
    skip = {int(x) for x in a.skip_pages.split(",") if x.strip()}
    src, report = extract(a.pdf, out, skip, a.dpi)
    print(f"work dir: {out}")
    print("\n".join(report))


if __name__ == "__main__":
    main()
