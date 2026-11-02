"""Markdown notes: anchors are GitHub-style heading slugs."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from slidenotes.errors import LockedError
from slidenotes.notes.base import Section, normalize
from slidenotes.util.files import read_text
from slidenotes.util.paths import display

_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_SETEXT1 = re.compile(r"^ {0,3}=+[ \t]*$")
_SETEXT2 = re.compile(r"^ {0,3}-+[ \t]*$")


def strip_inline(text: str) -> str:
    """Rendered text of an inline Markdown heading (approximate)."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("`", "")
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    return text.strip()


def github_slug(text: str) -> str:
    """`## One-hot maths` -> `one-hot-maths` (github-slugger rules)."""
    out: list[str] = []
    for ch in strip_inline(text).strip().lower():
        if ch == " ":
            out.append("-")
        elif ch in "-_":
            out.append(ch)
        elif unicodedata.category(ch)[0] in "LNM":
            out.append(ch)
    return "".join(out)


@dataclass
class Heading:
    line: int
    level: int
    text: str  # as written (closing #s removed)
    slug: str

    @property
    def plain(self) -> str:
        return strip_inline(self.text)


class MarkdownNotes:
    """Adapter for .md files. Read-only: anchors already exist as headings."""

    def __init__(self, path: Path):
        self.path = path
        self._lines: list[str] | None = None
        self._headings: list[Heading] | None = None
        self._skip: set[int] = set()

    # -- parsing -----------------------------------------------------------
    def lines(self) -> list[str]:
        if self._lines is None:
            try:
                self._lines = read_text(self.path).split("\n")
            except FileNotFoundError:
                raise
            except (OSError, UnicodeDecodeError) as e:
                raise LockedError(f"{display(self.path)}: cannot read notes ({e})") from e
        return self._lines

    def _parse_headings(self, lines: list[str]) -> list[tuple[int, int, str]]:
        found: list[tuple[int, int, str]] = []
        skip: set[int] = set()
        i = 0
        if lines and lines[0].strip() == "---":  # YAML front matter
            for j in range(1, len(lines)):
                if lines[j].strip() in ("---", "..."):
                    skip.update(range(0, j + 1))
                    i = j + 1
                    break
        fence: str | None = None
        while i < len(lines):
            line = lines[i]
            m = _FENCE.match(line)
            if fence:
                skip.add(i)
                if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                        and not line.strip()[len(m.group(1)):].strip():
                    fence = None
                i += 1
                continue
            if m:
                fence = m.group(1)
                skip.add(i)
                i += 1
                continue
            a = _ATX.match(line)
            if a:
                found.append((i, len(a.group(1)), (a.group(2) or "").strip()))
            elif (line.strip() and i + 1 < len(lines)
                  and (i == 0 or not lines[i - 1].strip())
                  and not re.match(r"^\s*([-*+>|]|\d+[.)])", line)
                  and not line.startswith(("    ", "\t"))):
                if _SETEXT1.match(lines[i + 1]):
                    found.append((i, 1, line.strip()))
                    skip.add(i + 1)
                    i += 2
                    continue
                if _SETEXT2.match(lines[i + 1]):
                    found.append((i, 2, line.strip()))
                    skip.add(i + 1)
                    i += 2
                    continue
            i += 1
        self._skip = skip
        return found

    def _slug(self, text: str) -> str:
        return github_slug(text)

    def headings(self) -> list[Heading]:
        if self._headings is None:
            counts: dict[str, int] = {}
            result: list[Heading] = []
            for line, level, text in self._parse_headings(self.lines()):
                base = self._slug(text)
                n = counts.get(base, 0)
                slug = base if n == 0 else f"{base}-{n}"
                counts[base] = n + 1
                result.append(Heading(line, level, text, slug))
            self._headings = result
        return self._headings

    # -- adapter interface -------------------------------------------------
    def _section(self, h: Heading) -> Section:
        return Section(label=h.plain, anchor=h.slug, level=h.level, index=h.line, kind="heading")

    def sections(self, all: bool = False) -> list[Section]:
        return [self._section(h) for h in self.headings()]

    def find(self, target: str) -> list[Section]:
        t = normalize(target)
        tf = t.casefold()
        hs = self.headings()
        tiers = [
            [h for h in hs if normalize(h.plain) == t or normalize(h.text) == t],
            [h for h in hs if normalize(h.plain).casefold() == tf],
            [h for h in hs if h.slug == t.lstrip("#")],
        ]
        for tier in tiers:
            if tier:
                return [self._section(h) for h in tier]
        # A paragraph (or heading) starting with the text -> its enclosing section.
        result: list[Heading] = []
        lines = self.lines()
        heading_at = {h.line: h for h in hs}
        current: Heading | None = None
        for i, line in enumerate(lines):
            if i in heading_at:
                current = heading_at[i]
                text = current.plain
            elif i in self._skip:
                continue
            else:
                text = strip_inline(re.sub(r"^\s*([-*+>]|\d+[.)])\s+", "", line))
            if current and tf and normalize(text).casefold().startswith(tf) and current not in result:
                result.append(current)
        return [self._section(h) for h in result]

    def ensure_anchor(self, section: Section, dry_run: bool = False) -> str:
        assert section.anchor is not None
        return section.anchor

    def _heading(self, anchor: str) -> Heading | None:
        for h in self.headings():
            if h.slug == anchor:
                return h
        return None

    def has_anchor(self, anchor: str) -> bool:
        return self._heading(anchor) is not None

    def label_for(self, anchor: str) -> str | None:
        h = self._heading(anchor)
        return h.plain if h else None

    def extract(self, anchor: str) -> str | None:
        h = self._heading(anchor)
        if h is None:
            return None
        hs = self.headings()
        end = len(self.lines())
        for other in hs:
            if other.line > h.line and other.level <= h.level:
                end = other.line
                break
        chunk = self.lines()[h.line:end]
        while chunk and not chunk[-1].strip():
            chunk.pop()
        return "\n".join(chunk)
