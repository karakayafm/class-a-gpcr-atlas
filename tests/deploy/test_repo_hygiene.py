#!/usr/bin/env python3
"""Guard against machine-local paths and credentials in the published repository.

pipeline/phase6b/prepare_gh_pages.py already carries the rules for this — patterns for home
directories, mount points, scratch directories and a range of credential formats. It only ever
applies them to the build outputs under releases/, never to this repository, which is just as
public. That gap let an absolute path to one author's working copy sit in a committed document.

This runs the same patterns over every file git tracks here. The patterns are imported rather
than copied, so a rule added for the release package protects this repository too.

    python3 tests/deploy/test_repo_hygiene.py
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "pipeline/phase6b/prepare_gh_pages.py"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail and not ok else ""))
    if not ok:
        failures.append(name)


def load_rules():
    """Import the release scanner for its pattern tables.

    main() is guarded, so importing binds the constants without running any gate.
    """
    spec = importlib.util.spec_from_file_location("prepare_gh_pages", SCANNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tracked_files() -> list[str]:
    result = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    print("Repository hygiene")

    if not SCANNER.exists():
        print("  SKIPPED  release scanner not present at %s" % SCANNER.relative_to(ROOT))
        print("           the pattern tables live there; nothing to check against")
        return 0

    rules = load_rules()
    patterns = [(p, what, "local path") for p, what in rules.LOCAL_PATH_PATTERNS]
    patterns += [(p, what, "credential") for p, what in rules.SECRET_PATTERNS]
    check("pattern tables load from the release scanner", len(patterns) > 0, str(len(patterns)))

    files = tracked_files()
    # The research workspace ignores everything, so a checkout there tracks no files at all.
    # Reporting that plainly beats printing a pass earned by scanning nothing.
    if not files:
        print("  SKIPPED  no tracked files; this is not the publication checkout")
        print("           run it where `git ls-files` lists the published tree")
        return 0

    scanned = 0
    hits: list[str] = []
    for rel in files:
        path = ROOT / rel
        if path.suffix not in rules.TEXT_SUFFIX or not path.is_file():
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        scanned += 1
        for pattern, what, kind in patterns:
            for match in re.finditer(pattern, text):
                line = text[:match.start()].count("\n") + 1
                hits.append("%s:%d  [%s: %s]  %s" % (rel, line, kind, what, match.group(0)[:60]))

    check("tracked text files were scanned", scanned > 0, str(scanned))
    check("no machine-local paths or credentials in tracked files", not hits,
          "\n          " + "\n          ".join(hits[:20]))

    print()
    if failures:
        print("total %d checks, %d failed" % (3, len(failures)))
        return 1
    print("repository hygiene: all checks passed (%d files scanned)" % scanned)
    return 0


if __name__ == "__main__":
    sys.exit(main())
