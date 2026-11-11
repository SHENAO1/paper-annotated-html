#!/usr/bin/env python3
"""Package the skill as dist/paper-annotated-html-<version>.zip for upload or a GitHub release.

    python tools/package.py [--out DIR]

The zip holds one top-level folder, paper-annotated-html/, without evals/ and caches.
The version comes from metadata.version in SKILL.md.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "paper-annotated-html"
SKILL = ROOT / NAME
SKIP_DIRS = {"evals", "__pycache__"}
SKIP_FILES = {".DS_Store"}


def version() -> str:
    head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("\n---\n", 1)[0]
    m = re.search(r'^\s+version:\s*"?([0-9][^"\s]*)"?\s*$', head, re.M)
    if not m:
        sys.exit("SKILL.md frontmatter has no metadata.version")
    return m.group(1)


def files():
    for p in sorted(SKILL.rglob("*")):
        rel = p.relative_to(SKILL)
        if p.is_file() and not SKIP_DIRS & set(rel.parts) and p.name not in SKIP_FILES and p.suffix != ".pyc":
            yield p, rel


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    a = ap.parse_args()
    out = a.out / f"{NAME}-{version()}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p, rel in files():
            z.write(p, f"{NAME}/{rel.as_posix()}")
            n += 1
        lic = ROOT / "LICENSE"
        if lic.is_file():
            z.write(lic, f"{NAME}/LICENSE")
            n += 1
    print(f"wrote {out} ({n} files, {out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
