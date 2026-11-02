"""Data model: Link rows and the Sidecar that holds them."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from slidenotes.core.slideset import SlideSet
from slidenotes.util.paths import resolve_rel, same_path, to_rel


@dataclass
class Link:
    """One row: a slide set joined to one anchor in one notes file."""

    slides: SlideSet
    notes: str  # path relative to the sidecar folder, forward slashes
    anchor: str
    label: str = ""

    def to_dict(self, base_dir: Path | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "slides": self.slides.format(),
            "slide_list": self.slides.expand(),
            "notes": self.notes,
            "anchor": self.anchor,
            "label": self.label,
        }
        if base_dir is not None:
            d["notes_path"] = str(resolve_rel(self.notes, base_dir))
        return d


@dataclass
class Sidecar:
    """`<source>.links.md`: YAML front matter, a link table, and free text kept verbatim."""

    path: Path
    meta: dict[str, Any]
    links: list[Link] = field(default_factory=list)
    prefix: str = ""  # body text before the table
    suffix: str = ""  # body text after the table

    @property
    def dir(self) -> Path:
        return self.path.parent

    @property
    def source_rel(self) -> str:
        return str(self.meta.get("source", ""))

    @property
    def source_path(self) -> Path:
        return resolve_rel(self.source_rel, self.dir)

    @property
    def source_name(self) -> str:
        return Path(self.source_rel).name

    @property
    def pages(self) -> int | None:
        v = self.meta.get("source_pages")
        return int(v) if isinstance(v, int) or (isinstance(v, str) and v.isdigit()) else None

    @property
    def notes(self) -> list[str]:
        v = self.meta.get("notes") or []
        return [str(x) for x in v] if isinstance(v, list) else [str(v)]

    def notes_path(self, rel: str) -> Path:
        return resolve_rel(rel, self.dir)

    def rel(self, path: Path) -> str:
        return to_rel(path, self.dir)

    def find_notes_rel(self, path: Path) -> str | None:
        for rel in self.notes:
            if same_path(self.notes_path(rel), path):
                return rel
        return None

    def add_notes(self, path: Path) -> tuple[str, bool]:
        existing = self.find_notes_rel(path)
        if existing is not None:
            return existing, False
        rel = self.rel(path)
        self.meta["notes"] = self.notes + [rel]
        return rel, True

    def replace_notes(self, old_rel: str, new_rel: str) -> None:
        self.meta["notes"] = [new_rel if r == old_rel else r for r in self.notes]
        for link in self.links:
            if link.notes == old_rel:
                link.notes = new_rel

    def same_notes(self, a: str, b: str) -> bool:
        return a == b or same_path(self.notes_path(a), self.notes_path(b))

    def sort_links(self) -> None:
        # Stable: ties keep their existing order.
        self.links.sort(key=lambda l: (l.slides.first, l.notes))

    def links_for(self, slide: int) -> list[Link]:
        return [l for l in self.links if slide in l.slides]
