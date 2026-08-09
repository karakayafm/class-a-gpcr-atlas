#!/usr/bin/env python3
"""Guard for scripts/sync_gh_pages.sh.

The published branch carries files the site build never produces — .nojekyll above all. A
mirroring `rsync --delete` removes them, and a missing .nojekyll changes how GitHub Pages serves
the site without any error. These tests build throwaway directories and assert that the script
keeps such files, and that it refuses to deploy rather than losing one.

    python3 tests/deploy/test_gh_pages_protection.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/sync_gh_pages.sh"
PROTECTED_LIST = ROOT / "config/gh_pages_protected.txt"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail and not ok else ""))
    if not ok:
        failures.append(name)


def protected_paths() -> list[str]:
    out = []
    for line in PROTECTED_LIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def run(site: Path, worktree: Path, protected_list: Path | None = None):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    if protected_list is not None:
        env["GH_PAGES_PROTECTED_LIST"] = str(protected_list)
    return subprocess.run([str(SCRIPT), str(site), str(worktree)],
                          capture_output=True, text=True, env=env)


def make_site(base: Path) -> Path:
    site = base / "site"
    (site / "js").mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (site / "js/app.js").write_text("// app", encoding="utf-8")
    return site


def main() -> int:
    check("sync script exists", SCRIPT.exists())
    check("protected list exists", PROTECTED_LIST.exists())
    if failures:
        return 1
    names = protected_paths()
    check("protected list includes .nojekyll", ".nojekyll" in names, str(names))

    # 1. Protected files survive a mirroring sync that would otherwise delete them.
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        site = make_site(base)
        wt = base / "wt"
        wt.mkdir()
        for name in names:
            (wt / name).write_text("keep me", encoding="utf-8")
        (wt / "stale.js").write_text("// removed build artefact", encoding="utf-8")
        result = run(site, wt)
        check("sync succeeds", result.returncode == 0, result.stderr[-300:])
        check("every protected file survives",
              all((wt / name).exists() for name in names),
              str([name for name in names if not (wt / name).exists()]))
        check("stale build artefact is still deleted", not (wt / "stale.js").exists())
        check("site content is mirrored", (wt / "js/app.js").exists())

    # 2. A protected file that is already missing stops the deploy instead of proceeding.
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        site = make_site(base)
        wt = base / "wt"
        wt.mkdir()
        for name in names[1:]:
            (wt / name).write_text("keep me", encoding="utf-8")
        result = run(site, wt)
        check("missing protected file aborts the deploy", result.returncode != 0,
              "exit=%s" % result.returncode)
        check("abort explains which path", names[0] in result.stderr, result.stderr[-300:])

    print()
    if failures:
        print("total %d checks, %d failed" % (11, len(failures)))
        return 1
    print("gh-pages protection: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
