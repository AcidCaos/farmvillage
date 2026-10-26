#!/usr/bin/env python3
"""Check repository-local Markdown targets without network or game resources."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
INLINE = re.compile(r'!?\[[^\]\n]*\]\((<[^>\n]+>|[^\s)]+)(?:\s+"[^"]*")?\)')
REFERENCE = re.compile(r'^\s*\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)', re.MULTILINE)


def check(root):
    root = root.resolve()
    failures = []
    checked = 0
    for path in sorted(root.rglob("*.md")):
        if any(part in {".git", ".venv", "venv", "node_modules"} for part in path.relative_to(root).parts):
            continue
        text = re.sub(r'^```[^\n]*\n.*?^```[^\S\n]*$', lambda match: "\n" * match.group(0).count("\n"), path.read_text(), flags=re.MULTILINE | re.DOTALL)
        for match in [*INLINE.finditer(text), *REFERENCE.finditer(text)]:
            target = match.group(1).strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            checked += 1
            relative = unquote(parsed.path)
            destination = (path.parent / relative).resolve()
            line = text.count("\n", 0, match.start()) + 1
            if relative.startswith("/") or not destination.is_relative_to(root):
                failures.append(f"{path.relative_to(root)}:{line}: nonportable target {target}")
            elif not destination.exists():
                failures.append(f"{path.relative_to(root)}:{line}: missing target {target}")
    return checked, failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args()
    count, failures = check(arguments.root)
    for failure in failures:
        print(failure)
    print(f"Checked {count} repository-local Markdown targets; {len(failures)} broken or nonportable.")
    raise SystemExit(bool(failures))
