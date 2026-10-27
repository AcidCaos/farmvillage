"""Keep wrapper-owned paths inside the configured data root without following links."""

from __future__ import annotations

import os
from pathlib import Path


def owned_path(root: Path, path: Path, *, allow_leaf_symlink: bool = False) -> Path:
    """Return a canonical-root path after checking every owned path component.

    The configured root itself is canonicalized (macOS also aliases /var to
    /private/var). Below that root, links are rejected before reads or mutations
    can follow them. The sole explicit exception is a venv's interpreter link.
    """
    lexical_root = Path(os.path.abspath(Path(root).expanduser()))
    canonical_root = lexical_root.resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = lexical_root / candidate
    candidate = Path(os.path.abspath(candidate))
    relative = None
    for anchor in (lexical_root, canonical_root):
        try:
            relative = candidate.relative_to(anchor)
            break
        except ValueError:
            continue
    if relative is None:
        raise RuntimeError(f"The owned data path escapes its configured folder: {candidate}")
    checked = canonical_root
    for index, component in enumerate(relative.parts):
        checked /= component
        if checked.is_symlink() and not (allow_leaf_symlink and index == len(relative.parts) - 1):
            raise RuntimeError(f"A symbolic link redirects an owned data path: {checked}. Move the link out of the data folder, then retry.")
    return checked
