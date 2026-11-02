"""`~/.slidenotes/library.md`: one row per registered sidecar. A cache that can be rebuilt."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from slidenotes.core import mdtable
from slidenotes.core import sidecar as sidecar_io
from slidenotes.core.model import Sidecar
from slidenotes.errors import SnError
from slidenotes.util import config
from slidenotes.util.files import atomic_write_text, read_text
from slidenotes.util.paths import abs_posix, md_dest, norm, parse_md_link, same_path

HEADER = ["Source", "Notes", "Links", "Sidecar"]
TITLE = "# SlideNotes library\n\n"
SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", ".slidenotes",
             ".tox", ".mypy_cache", ".pytest_cache", "site-packages"}


@dataclass
class LibraryEntry:
    source: Path
    notes: int
    links: int
    sidecar: Path

    def to_dict(self) -> dict:
        return {"source": str(self.source), "notes": self.notes, "links": self.links,
                "sidecar": str(self.sidecar)}


@dataclass
class Library:
    path: Path
    entries: list[LibraryEntry] = field(default_factory=list)
    prefix: str = TITLE
    suffix: str = ""

    @classmethod
    def load(cls, path: Path | None = None) -> "Library":
        path = path or config.library_path()
        if not path.exists():
            return cls(path=path)
        text = read_text(path)
        lines = text.splitlines(keepends=True)
        found = mdtable.find_table(lines, "Source")
        if found is None:
            return cls(path=path, prefix=text if text.endswith("\n\n") else TITLE)
        start, end = found
        entries: list[LibraryEntry] = []
        for k in range(start + 2, end):
            cells = mdtable.split_row(lines[k].rstrip("\n"))
            if len(cells) < 4:
                continue
            src = parse_md_link(cells[0])
            sc = parse_md_link(cells[3])
            if not sc:
                continue
            entries.append(LibraryEntry(
                source=Path(src[1] if src else cells[0]),
                notes=_int(cells[1]),
                links=_int(cells[2]),
                sidecar=Path(sc[1]),
            ))
        return cls(path=path, entries=entries, prefix="".join(lines[:start]), suffix="".join(lines[end:]))

    def render(self) -> str:
        rows = [
            [f"[{e.source.name}]({md_dest(abs_posix(e.source))})", str(e.notes), str(e.links),
             f"[{e.sidecar.name}]({md_dest(abs_posix(e.sidecar))})"]
            for e in self.entries
        ]
        prefix = self.prefix or TITLE
        return prefix + mdtable.render(HEADER, rows) + self.suffix

    def save(self) -> None:
        try:
            atomic_write_text(self.path, self.render())
        except OSError as e:
            raise SnError(f"{self.path}: cannot write library ({e})") from e

    def find(self, sidecar_path: Path) -> LibraryEntry | None:
        for e in self.entries:
            if same_path(e.sidecar, sidecar_path):
                return e
        return None

    def find_by_source(self, source: Path) -> LibraryEntry | None:
        for e in self.entries:
            if same_path(e.source, source):
                return e
        return None

    def upsert(self, sc: Sidecar) -> LibraryEntry:
        entry = LibraryEntry(source=norm(sc.source_path), notes=len(sc.notes), links=len(sc.links),
                             sidecar=norm(sc.path))
        for i, e in enumerate(self.entries):
            if same_path(e.sidecar, sc.path):
                self.entries[i] = entry
                return entry
        self.entries.append(entry)
        return entry

    def remove(self, sidecar_path: Path) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if not same_path(e.sidecar, sidecar_path)]
        return len(self.entries) != before


def _int(s: str) -> int:
    try:
        return int(s)
    except ValueError:
        return 0


def register(sc: Sidecar, dry_run: bool = False) -> None:
    lib = Library.load()
    lib.upsert(sc)
    if not dry_run:
        lib.save()


def scan(folder: Path, limit: int = 200_000) -> list[Path]:
    """Find *.links.md files below `folder`, skipping tool and VCS folders."""
    found: list[Path] = []
    seen = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            seen += 1
            if name.endswith(sidecar_io.SUFFIX):
                found.append(Path(root) / name)
        if seen > limit:
            break
    return found


def rebuild(extra_dirs: list[Path] | None = None) -> tuple[Library, list[str]]:
    """Rescan known folders (those of current entries, plus `extra_dirs`) and rebuild the library."""
    old = Library.load()
    dirs: list[Path] = []
    for d in [e.sidecar.parent for e in old.entries] + list(extra_dirs or []):
        d = norm(d)
        if d.is_dir() and not any(same_path(d, x) for x in dirs):
            dirs.append(d)
    new = Library(path=old.path, prefix=old.prefix, suffix=old.suffix)
    warnings: list[str] = []
    for d in dirs:
        for p in scan(d):
            if new.find(p):
                continue
            try:
                new.upsert(sidecar_io.read(p))
            except SnError as e:
                warnings.append(str(e))
    return new, warnings
