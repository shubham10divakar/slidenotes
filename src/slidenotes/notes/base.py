"""The NotesAdapter interface every notes format implements."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from slidenotes.errors import UsageError
from slidenotes.util.paths import display

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".docx"}


@dataclass
class Section:
    label: str          # heading or paragraph text
    anchor: str | None  # existing anchor id (slug or bookmark); None if a bookmark must be created
    level: int          # heading level 1-9; 0 for plain paragraphs
    index: int          # line number (md/txt) or paragraph index (docx)
    kind: str           # "heading" | "bookmark" | "bold" | "paragraph"

    def to_dict(self) -> dict:
        return {"label": self.label, "anchor": self.anchor, "level": self.level,
                "index": self.index, "kind": self.kind}


@runtime_checkable
class NotesAdapter(Protocol):
    path: Path

    def sections(self, all: bool = False) -> list[Section]: ...  # headings + existing anchors
    def find(self, target: str) -> list[Section]: ...             # candidates for TARGET
    def ensure_anchor(self, section: Section, dry_run: bool = False) -> str: ...
    def extract(self, anchor: str) -> str | None: ...             # section text, None if missing
    def label_for(self, anchor: str) -> str | None: ...
    def has_anchor(self, anchor: str) -> bool: ...


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def short_label(text: str, limit: int = 80) -> str:
    text = normalize(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]) + "…"


def adapter_for(path: Path) -> NotesAdapter:
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        from slidenotes.notes.markdown import MarkdownNotes
        return MarkdownNotes(path)
    if suffix == ".txt":
        from slidenotes.notes.text import TextNotes
        return TextNotes(path)
    if suffix == ".docx":
        from slidenotes.notes.docx import DocxNotes
        return DocxNotes(path)
    if suffix == ".doc":
        raise UsageError(f"{display(path)}: old .doc files are not supported; save it as .docx in Word")
    raise UsageError(f"{display(path)}: unsupported notes type {suffix or '(none)'} (use .docx, .md or .txt)")
