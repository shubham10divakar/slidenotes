"""Read and write `<source>.links.md` sidecars.

Layout: YAML front matter, then free text, the link table, more free text. Only the
front matter and the table are rewritten; the text around the table is kept verbatim.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from slidenotes import SIDECAR_FORMAT
from slidenotes.core import mdtable
from slidenotes.core.model import Link, Sidecar
from slidenotes.core.slideset import SlideSet, SlideSetError
from slidenotes.errors import UsageError, ValidationError
from slidenotes.util.files import atomic_write_text, read_text
from slidenotes.util.paths import display, md_dest, parse_md_link

SUFFIX = ".links.md"
HEADER = ["Slides", "Notes", "Anchor", "Label"]
FRAGMENT_SUFFIXES = {".md", ".markdown"}


class SidecarError(ValidationError):
    pass


class _Dumper(yaml.SafeDumper):
    """Indent list items under their key, as in the documented format."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):  # noqa: D401
        return super().increase_indent(flow, False)


def sidecar_path_for(source: Path) -> Path:
    return source.with_name(source.stem + SUFFIX)


def is_sidecar_path(path: Path) -> bool:
    return path.name.endswith(SUFFIX)


def new_sidecar(source: Path, sha256: str, pages: int | None) -> Sidecar:
    path = sidecar_path_for(source)
    meta: dict[str, Any] = {
        "slidenotes": SIDECAR_FORMAT,
        "source": source.name,
        "source_sha256": sha256,
        "source_pages": pages,
        "notes": [],
    }
    return Sidecar(path=path, meta=meta, links=[], prefix=f"\n# Links: {source.name}\n\n", suffix="")


def _split_front_matter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise SidecarError(f"{display(path)}: missing YAML front matter (must start with ---)")
    end = text.find("\n---\n", 3)
    if end == -1:
        if text.endswith("\n---"):
            end = len(text) - 4
            body = ""
        else:
            raise SidecarError(f"{display(path)}: front matter is not closed with ---")
    else:
        body = text[end + 5:]
    try:
        meta = yaml.safe_load(text[4:end + 1]) or {}
    except yaml.YAMLError as e:
        raise SidecarError(f"{display(path)}: invalid YAML front matter ({e})") from e
    if not isinstance(meta, dict):
        raise SidecarError(f"{display(path)}: front matter must be a mapping")
    return meta, body


def parse(text: str, path: Path) -> Sidecar:
    meta, body = _split_front_matter(text, path)
    if "source" not in meta:
        raise SidecarError(f"{display(path)}: front matter has no 'source'")
    lines = body.splitlines(keepends=True)
    found = mdtable.find_table(lines, "Slides")
    if found is None:
        return Sidecar(path=path, meta=meta, links=[], prefix=body, suffix="")
    start, end = found
    header_lines = len(text) - len(body)
    line_offset = text[:header_lines].count("\n") + 1
    header = [h.casefold() for h in mdtable.split_row(lines[start].rstrip("\n"))]

    def col(name: str) -> int | None:
        return header.index(name) if name in header else None

    ci_s, ci_n, ci_a, ci_l = col("slides"), col("notes"), col("anchor"), col("label")
    if ci_s is None or ci_n is None or ci_a is None:
        raise SidecarError(f"{display(path)}: link table needs Slides, Notes and Anchor columns")
    links: list[Link] = []
    for k in range(start + 2, end):
        raw = lines[k].rstrip("\n")
        cells = mdtable.split_row(raw)
        lineno = line_offset + k
        if all(not c for c in cells):
            continue

        def cell(i: int | None) -> str:
            return cells[i] if i is not None and i < len(cells) else ""

        try:
            slides = SlideSet.parse(cell(ci_s))
        except SlideSetError as e:
            raise SidecarError(f"{display(path)}:{lineno}: {e.message}") from e
        notes_cell = cell(ci_n)
        parsed = parse_md_link(notes_cell)
        notes = parsed[1] if parsed else notes_cell
        notes = notes.split("#", 1)[0].strip()
        anchor = cell(ci_a).strip()
        if not notes or not anchor:
            raise SidecarError(f"{display(path)}:{lineno}: row needs a notes file and an anchor")
        links.append(Link(slides=slides, notes=notes, anchor=anchor, label=cell(ci_l)))
    return Sidecar(
        path=path,
        meta=meta,
        links=links,
        prefix="".join(lines[:start]),
        suffix="".join(lines[end:]),
    )


def read(path: Path) -> Sidecar:
    try:
        text = read_text(path)
    except FileNotFoundError as e:
        raise UsageError(f"{display(path)}: sidecar not found") from e
    except (OSError, UnicodeDecodeError) as e:
        raise SidecarError(f"{display(path)}: cannot read sidecar ({e})") from e
    return parse(text, path)


def _notes_cell(link: Link) -> str:
    name = Path(link.notes).name
    dest = link.notes
    if Path(link.notes).suffix.lower() in FRAGMENT_SUFFIXES:
        dest = f"{dest}#{link.anchor}"
    return f"[{name}]({md_dest(dest)})"


def render(sidecar: Sidecar) -> str:
    sidecar.sort_links()
    front = yaml.dump(sidecar.meta, Dumper=_Dumper, sort_keys=False, allow_unicode=True,
                      default_flow_style=False, width=10_000)
    rows = [[l.slides.format(), _notes_cell(l), l.anchor, l.label] for l in sidecar.links]
    prefix = sidecar.prefix
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix and not prefix.endswith("\n\n"):
        prefix += "\n"
    return "---\n" + front + "---\n" + prefix + mdtable.render(HEADER, rows) + sidecar.suffix


def write(sidecar: Sidecar) -> None:
    atomic_write_text(sidecar.path, render(sidecar))
