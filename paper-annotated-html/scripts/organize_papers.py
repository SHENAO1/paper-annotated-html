#!/usr/bin/env python3
"""Sort a paper library into done/ (finished with this skill) and todo/ (not yet).

    python organize_papers.py LIBRARY [--dry-run]

Library layout:
    LIBRARY/todo/<paper>.pdf          not finished yet; extract_pdf.py puts <slug>_work/ next to it
    LIBRARY/done/<slug>/              finished: the PDF, its _work/ and <title>.annotated.html together
    LIBRARY/<paper>.pdf               a loose drop-in; filed into todo/ or done/ on the next run

A paper counts as finished when build_html.py has done a full, error-free build:
<slug>_work/built.json exists and names an .annotated.html that sits next to the PDF.
A preview built with --allow-partial or --sections does not count.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def pdf_slug(pdf: Path) -> str:
    # same rule as extract_pdf.py, so <slug>_work/ is found
    return re.sub(r"[^A-Za-z0-9]+", "-", pdf.stem).strip("-")[:40].strip("-") or "paper"


def find_work(pdf: Path) -> Path:
    """<slug>_work/ by default; a work dir made with --out is matched by source.json meta.pdf."""
    default = pdf.parent / f"{pdf_slug(pdf)}_work"
    if default.is_dir():
        return default
    for d in sorted(pdf.parent.glob("*_work")):
        try:
            if json.loads((d / "source.json").read_text(encoding="utf-8"))["meta"]["pdf"] == pdf.name:
                return d
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return default


def built_html(pdf: Path, work: Path) -> Path | None:
    marker = work / "built.json"
    if not marker.is_file():
        return None
    try:
        name = json.loads(marker.read_text(encoding="utf-8")).get("html")
    except (OSError, ValueError):
        return None
    html = pdf.parent / name if name else None
    return html if html and html.is_file() else None


def default_html(pdf: Path, work: Path) -> Path | None:
    """Where build_html.py writes by default (also previews) - same rule as build_html.py."""
    try:
        title = json.loads((work / "source.json").read_text(encoding="utf-8"))["meta"].get("title") or "Untitled"
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")[:50].strip("-") or "paper"
    html = pdf.parent / f"{slug}.annotated.html"
    return html if html.is_file() else None


def progress(work: Path) -> str:
    if not work.is_dir():
        return "未开始"
    src = work / "source.json"
    if not src.is_file():
        return "已抽取（缺 source.json）"
    try:
        proofread = json.loads(src.read_text(encoding="utf-8")).get("proofread")
    except ValueError:
        proofread = False
    if not proofread:
        return "待校对"
    if (work / "built.json").is_file():
        return "已构建，但找不到 HTML"
    annot = work / "annot"
    n = len(list(annot.glob("S*.json"))) if annot.is_dir() else 0
    return f"批注中（已写 {n} 节）"


def move(src: Path, dst_dir: Path, lib: Path, dry: bool, log: list[str]) -> bool:
    dst = dst_dir / src.name
    if dst.exists():
        log.append(f"  跳过：{dst.relative_to(lib)} 已存在")
        return False
    log.append(f"  {src.name}  →  {dst_dir.relative_to(lib)}/")
    if not dry:
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("library", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="only print what would move")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    lib = a.library.resolve()
    todo, done = lib / "todo", lib / "done"
    if not a.dry_run:
        todo.mkdir(parents=True, exist_ok=True)
        done.mkdir(parents=True, exist_ok=True)

    log: list[str] = []
    candidates = sorted(lib.glob("*.pdf")) + sorted(todo.glob("*.pdf"))
    for pdf in candidates:
        slug = pdf_slug(pdf)
        work = find_work(pdf)
        html = built_html(pdf, work)
        if html:
            dest = done / slug
            if dest.exists():
                log.append(f"[完成] {pdf.name}: 跳过，{dest} 已存在")
                continue
            log.append(f"[完成] {pdf.name}")
            for f in (pdf, work, html):
                if f.exists():
                    move(f, dest, lib, a.dry_run, log)
        elif pdf.parent == lib:
            log.append(f"[未完成] {pdf.name}")
            for f in (pdf, work, default_html(pdf, work)):   # a preview HTML goes along
                if f and f.exists():
                    move(f, todo, lib, a.dry_run, log)

    for line in log:
        print(line)
    if not log:
        print("没有需要移动的论文。")

    # summary, as it will look after the moves
    print("\n== done/（已用技能完成）==")
    finished = sorted(p for p in done.iterdir() if p.is_dir()) if done.is_dir() else []
    for d in finished:
        htmls = list(d.glob("*.annotated.html"))
        print(f"  {d.name}/" + ("" if htmls else "   ⚠ 没有 .annotated.html"))
    if a.dry_run:
        print("  （--dry-run：上面将移入的论文未计入）")
    print("\n== todo/（尚未完成）==")
    pending = sorted(todo.glob("*.pdf")) if todo.is_dir() else []
    for pdf in pending:
        print(f"  {pdf.name}   {progress(find_work(pdf))}")
    if a.dry_run:
        print("  （--dry-run：上面将移入的论文未计入）")
    print(f"\n完成 {len(finished)} 篇，未完成 {len(pending)} 篇")


if __name__ == "__main__":
    main()
