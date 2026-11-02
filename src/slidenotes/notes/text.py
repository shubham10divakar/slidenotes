"""Plain-text notes: a line starting with `#` is a heading; `##` is one level deeper."""

from __future__ import annotations

import re

from slidenotes.notes.markdown import MarkdownNotes

_HEAD = re.compile(r"^(#+)[ \t]*(\S.*?)[ \t]*$")


class TextNotes(MarkdownNotes):
    def _parse_headings(self, lines: list[str]) -> list[tuple[int, int, str]]:
        self._skip = set()
        found: list[tuple[int, int, str]] = []
        for i, line in enumerate(lines):
            m = _HEAD.match(line)
            if m:
                found.append((i, len(m.group(1)), m.group(2)))
        return found
