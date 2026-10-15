#!/usr/bin/env python3
"""Fails when a change to a CHANGELOG.md lands outside its [Unreleased] section.

    python3 infra/scripts/changelog_unreleased.py <base> [<head>]

Compares <head> (default HEAD) with <base> for every CHANGELOG.md in the
repository. Every added line must sit under `## [Unreleased]` in the new
file, every removed line under `## [Unreleased]` in the old one; a line's
section is the nearest `## [` heading at or above it. A rebase over a
release roll tends to leave a new line under the section just released,
which this catches. Release pull requests, which move lines out of
[Unreleased] on purpose, are exempted by the workflow, not here.

Exit 0: every change is inside [Unreleased]; 1: a line is not, each one
named with its file, line number and section; 2: git failed.
"""

from __future__ import annotations

import re
import subprocess
import sys

UNRELEASED = "Unreleased"
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
HEADING = re.compile(r"^## \[([^\]]+)\]")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def changelogs(base: str, head: str) -> list[str]:
    names = git("diff", "--name-only", base, head, "--", "CHANGELOG.md", "*/CHANGELOG.md")
    return [n for n in names.splitlines() if n]


def content(ref: str, path: str) -> list[str]:
    try:
        return git("show", f"{ref}:{path}").splitlines()
    except subprocess.CalledProcessError:
        return []  # the file does not exist on that side


def section(lines: list[str], number: int) -> str | None:
    """The section of 1-based line `number`: the nearest `## [x]` heading at or above it."""
    for line in reversed(lines[:number]):
        m = HEADING.match(line)
        if m:
            return m.group(1)
    return None


def changed_lines(base: str, head: str, path: str) -> list[tuple[str, int, str]]:
    """(side, line number on that side, text) for every added ('+') and removed ('-') line."""
    out = []
    old = new = 0
    for line in git("diff", "-U0", base, head, "--", path).splitlines():
        m = HUNK.match(line)
        if m:
            old, new = int(m.group(1)), int(m.group(3))
            continue
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("-"):
            out.append(("-", old, line[1:]))
            old += 1
        elif line.startswith("+"):
            out.append(("+", new, line[1:]))
            new += 1
    return out


def violations(base: str, head: str) -> list[str]:
    problems = []
    for path in changelogs(base, head):
        before, after = content(base, path), content(head, path)
        for side, number, text in changed_lines(base, head, path):
            lines = after if side == "+" else before
            where = section(lines, number)
            if where != UNRELEASED:
                kind = "added" if side == "+" else "removed"
                place = f"[{where}]" if where else "above the first section"
                problems.append(
                    f"{path}:{number}: {kind} line is under {place}, not [{UNRELEASED}]: "
                    f"{text.strip()[:100]}"
                )
    return problems


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2):
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    base, head = argv[0], argv[1] if len(argv) == 2 else "HEAD"
    try:
        problems = violations(base, head)
    except subprocess.CalledProcessError as exc:
        print(f"git failed: {exc.stderr.strip()}", file=sys.stderr)
        return 2
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        print(
            f"{len(problems)} CHANGELOG line(s) outside [{UNRELEASED}]: move them under "
            f"## [{UNRELEASED}] (a release pull request or the label changelog-fix is exempt)",
            file=sys.stderr,
        )
        return 1
    print(f"every CHANGELOG change is inside [{UNRELEASED}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
