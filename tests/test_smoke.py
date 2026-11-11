"""Smoke tests: every script runs end to end on a synthetic paper (no copyrighted text).

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "paper-annotated-html" / "scripts"
FIXTURE = Path(__file__).resolve().parent / "fixture" / "sample_work"

try:
    import fitz  # noqa: F401
    HAVE_FITZ = True
except ImportError:
    HAVE_FITZ = False


def run(*args, ok=True):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, encoding="utf-8", env=env)
    if ok and r.returncode != 0:
        raise AssertionError(f"{args} exited {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pah-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def library_with_sample(self) -> Path:
        lib = self.tmp / "papers"
        (lib / "todo").mkdir(parents=True)
        (lib / "done").mkdir()
        (lib / "todo" / "sample.pdf").write_bytes(b"%PDF-1.4 placeholder\n")
        shutil.copytree(FIXTURE, lib / "todo" / "sample_work")
        return lib


class BuildTests(Base):
    def test_check_status_dump(self):
        r = run(SCRIPTS / "build_html.py", FIXTURE, "--check")
        self.assertIn("0 error(s)", r.stdout)
        self.assertIn("NEXT:", run(SCRIPTS / "build_html.py", FIXTURE, "--status").stdout)
        self.assertIn("[S1.P1]", run(SCRIPTS / "build_html.py", FIXTURE, "--dump", "S1").stdout)

    def test_full_build_marks_done_and_organizer_files_it(self):
        lib = self.library_with_sample()
        work = lib / "todo" / "sample_work"
        run(SCRIPTS / "build_html.py", work)
        marker = json.loads((work / "built.json").read_text(encoding="utf-8"))
        html = lib / "todo" / marker["html"]
        self.assertTrue(html.is_file())
        page = html.read_text(encoding="utf-8")
        self.assertIn("一种自适应死区控制的示例变换器", page)
        self.assertIn('id="overview"', page)

        out = run(SCRIPTS / "organize_papers.py", lib).stdout
        self.assertIn("完成 1 篇，未完成 0 篇", out)
        done = lib / "done" / "sample"
        for name in ("sample.pdf", "sample_work", marker["html"]):
            self.assertTrue((done / name).exists(), name)
        self.assertEqual(list((lib / "todo").iterdir()), [])
        self.assertIn("没有需要移动的论文", run(SCRIPTS / "organize_papers.py", lib).stdout)

    def test_preview_is_not_done(self):
        lib = self.library_with_sample()
        work = lib / "todo" / "sample_work"
        run(SCRIPTS / "build_html.py", work)
        run(SCRIPTS / "build_html.py", work, "--allow-partial", "--sections", "S0")   # overwrites the full build
        self.assertFalse((work / "built.json").exists())
        out = run(SCRIPTS / "organize_papers.py", lib).stdout
        self.assertIn("完成 0 篇，未完成 1 篇", out)

    def test_loose_pdf_goes_to_todo(self):
        lib = self.tmp / "papers"
        lib.mkdir()
        (lib / "new paper.pdf").write_bytes(b"%PDF-1.4 placeholder\n")
        out = run(SCRIPTS / "organize_papers.py", lib).stdout
        self.assertTrue((lib / "todo" / "new paper.pdf").is_file())
        self.assertIn("未开始", out)


@unittest.skipUnless(HAVE_FITZ, "pymupdf not installed")
class ExtractTests(Base):
    def test_extract_generated_pdf(self):
        import fitz
        pdf = self.tmp / "generated.pdf"
        doc = fitz.open()
        for n in range(2):
            page = doc.new_page()
            page.insert_text((72, 80), "A Generated Test Paper" if n == 0 else "II. METHOD", fontsize=16)
            body = ("This page holds a few sentences of made-up body text so that the extractor "
                    "has a paragraph to find. It continues on a second line to form a block. ")
            page.insert_textbox(fitz.Rect(72, 110, 520, 400), body * 3, fontsize=10)
        doc.save(pdf)
        run(SCRIPTS / "extract_pdf.py", pdf)
        work = self.tmp / "generated_work"
        src = json.loads((work / "source.json").read_text(encoding="utf-8"))
        self.assertTrue(src["sections"])
        self.assertEqual(src["meta"]["pdf"], "generated.pdf")
        self.assertTrue(list((work / "pages").glob("*.png")))


class PackagingTests(Base):
    def test_package(self):
        r = run(ROOT / "tools" / "package.py", "--out", self.tmp)
        zips = list(self.tmp.glob("paper-annotated-html-*.zip"))
        self.assertEqual(len(zips), 1, r.stdout)
        names = zipfile.ZipFile(zips[0]).namelist()
        self.assertIn("paper-annotated-html/SKILL.md", names)
        self.assertIn("paper-annotated-html/scripts/organize_papers.py", names)
        self.assertFalse([n for n in names if "/evals/" in n or "__pycache__" in n])

    def test_install_link_and_copy(self):
        skills = self.tmp / "skills"
        target = skills / "paper-annotated-html"
        # runs before the temp dir is deleted, so a leftover junction is never followed into the repo
        self.addCleanup(run, ROOT / "install.py", "--dest", skills, "--uninstall", ok=False)
        run(ROOT / "install.py", "--dest", skills)
        self.assertTrue((target / "SKILL.md").is_file())
        self.assertIn("已是最新", run(ROOT / "install.py", "--dest", skills).stdout)
        run(ROOT / "install.py", "--dest", skills, "--copy")
        self.assertTrue((target / ".installed-by-paper-annotated-html").is_file())
        self.assertFalse((target / "evals").exists())
        run(ROOT / "install.py", "--dest", skills, "--uninstall")
        self.assertFalse(target.exists())
        self.assertTrue((ROOT / "paper-annotated-html" / "SKILL.md").is_file())


if __name__ == "__main__":
    unittest.main()
