#!/usr/bin/env python3
"""Install the paper-annotated-html skill into the skill folders of AI agents.

    python install.py                      install into every supported agent found on this machine
    python install.py --agent codex        only these agents (repeatable): claude, codex, workbuddy
    python install.py --dest DIR           any other agent: DIR is its skills folder
    python install.py --copy               copy instead of link (for agents that do not follow links)
    python install.py --uninstall          remove what this script installed
    python install.py --list               show where each agent keeps skills and what is there
    python install.py --dry-run            print what would happen, change nothing

By default the skill is linked (a junction on Windows, a symlink elsewhere), so `git pull`
updates every agent at once. A folder that this script did not create is never deleted:
with --force it is renamed to <name>.bak-<time> first.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

NAME = "paper-annotated-html"
SRC = Path(__file__).resolve().parent / NAME
MARKER = ".installed-by-paper-annotated-html"     # inside a copied install
COPY_IGNORE = shutil.ignore_patterns("evals", "__pycache__", "*.pyc", ".DS_Store")


def agent_dirs() -> dict[str, tuple[Path, Path]]:
    """agent -> (its home folder, which tells us it is installed; its skills folder)."""
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    return {
        "claude": (home / ".claude", home / ".claude" / "skills"),
        "codex": (codex_home, codex_home / "skills"),
        "workbuddy": (home / ".workbuddy", home / ".workbuddy" / "skills"),
    }


def is_link(p: Path) -> bool:
    try:
        os.readlink(p)        # symlinks everywhere, junctions on Windows (Python 3.8+)
        return True
    except (OSError, ValueError, NotImplementedError):
        return False


def points_to_us(p: Path) -> bool:
    return os.path.normcase(os.path.realpath(p)) == os.path.normcase(str(SRC))


def describe(target: Path) -> str:
    if is_link(target):
        return "已链接到本仓库" if points_to_us(target) else f"链接到别处：{os.path.realpath(target)}"
    if (target / MARKER).is_file():
        return "已复制安装"
    if target.exists():
        return "已存在（不是本脚本安装的）"
    return "未安装"


def remove_link(p: Path):
    if os.name == "nt" and p.is_dir():
        os.rmdir(p)           # removes a junction or directory symlink, never its contents
    else:
        p.unlink()


def make_link(target: Path):
    if os.name == "nt":
        # a junction needs no admin rights or developer mode, unlike a symlink
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(SRC)], capture_output=True, text=True)
        if r.returncode != 0:
            raise OSError(r.stdout.strip() or r.stderr.strip() or "mklink /J failed")
    else:
        os.symlink(SRC, target, target_is_directory=True)


def clear(target: Path, force: bool, dry: bool) -> bool:
    """Make room at target. Returns False when something there must not be touched."""
    if is_link(target):
        if not points_to_us(target) and not force:
            print(f"  跳过：{target} 链接到别处，加 --force 替换")
            return False
        if not dry:
            remove_link(target)
    elif (target / MARKER).is_file():
        if not dry:
            shutil.rmtree(target)          # our own earlier copy
    elif target.exists():
        if not force:
            print(f"  跳过：{target} 已存在且不是本脚本安装的，加 --force 先把它改名备份")
            return False
        backup = target.with_name(f"{target.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
        print(f"  备份：{target.name} → {backup.name}")
        if not dry:
            target.rename(backup)
    return True


def install(skills: Path, copy: bool, force: bool, dry: bool):
    target = skills / NAME
    if not copy and is_link(target) and points_to_us(target):
        print(f"  已是最新：{target}")
        return
    if not clear(target, force, dry):
        return
    if not dry:
        skills.mkdir(parents=True, exist_ok=True)
        if copy:
            shutil.copytree(SRC, target, ignore=COPY_IGNORE)
            (target / MARKER).write_text(f"copied from {SRC}\n", encoding="utf-8")
        else:
            make_link(target)
    print(f"  {'复制' if copy else '链接'}：{target}")


def uninstall(skills: Path, dry: bool):
    target = skills / NAME
    if is_link(target) and points_to_us(target):
        if not dry:
            remove_link(target)
        print(f"  已移除链接：{target}")
    elif (target / MARKER).is_file():
        if not dry:
            shutil.rmtree(target)
        print(f"  已移除复制：{target}")
    elif target.exists() or is_link(target):
        print(f"  保留：{target} 不是本脚本安装的")
    else:
        print(f"  未安装：{target}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", action="append", choices=sorted(agent_dirs()), help="repeatable")
    ap.add_argument("--dest", action="append", type=Path, metavar="DIR", help="another agent's skills folder")
    ap.add_argument("--copy", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if not (SRC / "SKILL.md").is_file():
        sys.exit(f"找不到技能目录：{SRC}")

    agents = agent_dirs()
    if a.list:
        for name, (home, skills) in agents.items():
            state = describe(skills / NAME) if home.is_dir() else "本机未安装该 Agent"
            print(f"{name:10} {skills}   {state}")
        return

    targets: list[tuple[str, Path]] = []
    if a.agent:
        targets += [(n, agents[n][1]) for n in a.agent]
    targets += [(str(d), d.expanduser()) for d in a.dest or []]
    if not targets:
        targets = [(n, skills) for n, (home, skills) in agents.items() if home.is_dir()]
        if not targets:
            sys.exit("没找到 Claude Code、Codex 或 WorkBuddy。用 --dest 指定其他 Agent 的技能目录。")

    if a.dry_run:
        print("（--dry-run：只打印，不改动）")
    for label, skills in targets:
        print(f"[{label}]")
        if a.uninstall:
            uninstall(skills, a.dry_run)
        else:
            install(skills, a.copy, a.force, a.dry_run)
    if not a.uninstall:
        print("\n依赖：pip install -r " + str(SRC / "requirements.txt"))
        print("装好后重启 Agent，让它重新扫描技能。")


if __name__ == "__main__":
    main()
