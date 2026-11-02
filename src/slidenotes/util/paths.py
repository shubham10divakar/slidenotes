"""Path helpers: relative paths stored in sidecars, Markdown link destinations, shell quoting."""

from __future__ import annotations

import os
import re
from pathlib import Path


def norm(path: Path | str) -> Path:
    """Absolute, normalised path without resolving symlinks."""
    return Path(os.path.normpath(os.path.abspath(path)))


def same_path(a: Path | str, b: Path | str) -> bool:
    return os.path.normcase(str(norm(a))) == os.path.normcase(str(norm(b)))


def to_rel(target: Path | str, base_dir: Path | str) -> str:
    """Path of `target` relative to `base_dir`, with forward slashes.

    Falls back to an absolute path when no relative path exists (different drives on Windows).
    """
    try:
        rel = os.path.relpath(norm(target), norm(base_dir))
    except ValueError:
        return norm(target).as_posix()
    return Path(rel).as_posix()


def resolve_rel(rel: str, base_dir: Path | str) -> Path:
    p = Path(rel)
    if not p.is_absolute():
        p = Path(base_dir) / p
    return norm(p)


def abs_posix(path: Path | str) -> str:
    return norm(path).as_posix()


def md_dest(dest: str) -> str:
    """A Markdown link destination; wrapped in <...> when it contains spaces or parentheses."""
    if re.search(r"[\s()<>]", dest):
        return f"<{dest}>"
    return dest


_LINK_RE = re.compile(r"^\s*\[((?:\\.|[^\]\\])*)\]\(\s*(<[^>]*>|[^\s)]*)\s*\)\s*$")


def parse_md_link(cell: str) -> tuple[str, str] | None:
    """Parse `[text](dest)`; returns (text, dest) or None if the cell is not a single link."""
    m = _LINK_RE.match(cell)
    if not m:
        return None
    dest = m.group(2)
    if dest.startswith("<") and dest.endswith(">"):
        dest = dest[1:-1]
    return m.group(1), dest


def shell_quote(value: Path | str) -> str:
    s = str(value)
    if s and re.fullmatch(r"[\w./\\:@%+=,-]+", s):
        return s
    return '"' + s.replace('"', '\\"') + '"'


def display(path: Path | str) -> str:
    """Short form for messages: relative to the current folder when below it."""
    p = norm(path)
    try:
        return p.relative_to(norm(Path.cwd())).as_posix()
    except ValueError:
        return p.as_posix()
