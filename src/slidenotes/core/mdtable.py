"""Minimal pipe-table reading/writing shared by the sidecar and the library."""

from __future__ import annotations

import re

_SEP_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")


def split_row(line: str) -> list[str]:
    """Split `| a | b \\| c |` into cells, honouring escaped pipes."""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def escape_cell(text: str) -> str:
    return text.replace("\n", " ").replace("|", "\\|").strip()


def is_separator(line: str) -> bool:
    return bool(_SEP_RE.match(line)) and "-" in line


def find_table(lines: list[str], first_header: str) -> tuple[int, int] | None:
    """Locate a table whose first header cell is `first_header` (case-insensitive).

    `lines` keep their line endings. Returns (header_index, end_index_exclusive).
    """
    want = first_header.casefold()
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("|"):
            continue
        cells = split_row(line.rstrip("\n"))
        if not cells or cells[0].casefold() != want:
            continue
        if i + 1 >= len(lines) or not is_separator(lines[i + 1].rstrip("\n")):
            continue
        j = i + 2
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            j += 1
        return i, j
    return None


def render(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |"]
    out.append("|" + "|".join("-" * (len(h) + 2) for h in header) + "|")
    for row in rows:
        out.append("| " + " | ".join(escape_cell(c) for c in row) + " |")
    return "\n".join(out) + "\n"
