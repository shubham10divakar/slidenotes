"""Operations behind the CLI commands. They return plain data; cli.py renders it."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from slidenotes.core import library as lib_mod
from slidenotes.core import sidecar as sidecar_io
from slidenotes.core.model import Link, Sidecar
from slidenotes.core.slideset import SlideSet
from slidenotes.errors import AmbiguousTarget, SnError, UsageError
from slidenotes.notes import SUPPORTED_SUFFIXES as NOTES_SUFFIXES
from slidenotes.notes import Section, adapter_for
from slidenotes.notes.base import short_label
from slidenotes.sources import source_for
from slidenotes.util.paths import display, norm, same_path, shell_quote

Confirm = Callable[[str], bool]


# -- locating ---------------------------------------------------------------
def load_sidecar(source_arg: str | Path) -> Sidecar:
    """SOURCE may be the source file or its sidecar; falls back to the library for moved sources."""
    p = norm(Path(source_arg))
    if sidecar_io.is_sidecar_path(p):
        return sidecar_io.read(p)
    sc_path = sidecar_io.sidecar_path_for(p)
    if sc_path.exists():
        sc = sidecar_io.read(sc_path)
        if same_path(sc.source_path, p) or not sc.source_path.exists():
            return sc
    entry = lib_mod.Library.load().find_by_source(p)
    if entry and entry.sidecar.exists():
        return sidecar_io.read(entry.sidecar)
    if sc_path.exists():
        return sidecar_io.read(sc_path)
    if not p.exists():
        raise UsageError(f"{display(p)}: file not found")
    raise UsageError(f"{display(p)}: not registered", fix=f"sn add {shell_quote(display(p))} --notes NOTES")


def save(sc: Sidecar, dry_run: bool) -> None:
    if not dry_run:
        sidecar_io.write(sc)
        lib_mod.register(sc)


def resolve_notes(sc: Sidecar, notes_arg: str | None) -> tuple[str, Path]:
    src = shell_quote(display(sc.source_path))
    if not sc.notes:
        raise UsageError(f"{sc.source_name}: no notes files registered", fix=f"sn add {src} --notes NOTES")
    if notes_arg is None:
        rel = sc.notes[0]
        return rel, sc.notes_path(rel)
    arg_path = norm(Path(notes_arg))
    by_path = [r for r in sc.notes if same_path(sc.notes_path(r), arg_path) or r == notes_arg.replace("\\", "/")]
    if by_path:
        return by_path[0], sc.notes_path(by_path[0])
    by_name = [r for r in sc.notes if Path(r).name.casefold() == Path(notes_arg).name.casefold()]
    if len(by_name) == 1:
        return by_name[0], sc.notes_path(by_name[0])
    if len(by_name) > 1:
        raise UsageError(f"{notes_arg}: several registered notes files have this name ({', '.join(by_name)}); "
                         "give the path instead")
    raise UsageError(f"{notes_arg}: not a notes file of {sc.source_name}",
                     fix=f"sn add {src} --notes {shell_quote(notes_arg)}")


def require_file(path: Path, what: str = "file") -> None:
    if not path.exists():
        raise UsageError(f"{display(path)}: {what} not found (moved or renamed?)", fix="sn check --fix")


# -- add ----------------------------------------------------------------------
@dataclass
class AddResult:
    sidecar: Sidecar
    created: bool
    added_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def add(source: Path, notes: list[Path], dry_run: bool = False) -> AddResult:
    source = norm(source)
    if not source.exists():
        raise UsageError(f"{display(source)}: file not found")
    adapter = source_for(source)
    warnings: list[str] = []
    sc_path = sidecar_io.sidecar_path_for(source)
    created = not sc_path.exists()
    if created:
        sc = sidecar_io.new_sidecar(source, adapter.sha256(), adapter.page_count())
        warnings += adapter.warnings
    else:
        sc = sidecar_io.read(sc_path)
        if not same_path(sc.source_path, source) and sc.source_path.exists():
            raise UsageError(f"{display(sc_path)} already belongs to {sc.source_rel}; "
                             f"rename {source.name} to register it")
        if not sc.source_path.exists() or not same_path(sc.source_path, source):
            sc.meta["source"] = sc.rel(source)
        if sc.meta.get("source_sha256") != adapter.sha256():
            warnings.append(f"{source.name}: source changed since it was registered; slide numbers may have shifted"
                            f" → run sn check {shell_quote(display(source))}")
    added: list[str] = []
    for n in notes:
        n = norm(n)
        if not n.exists():
            raise UsageError(f"{display(n)}: notes file not found")
        if n.suffix.lower() not in NOTES_SUFFIXES:
            raise UsageError(f"{display(n)}: unsupported notes type {n.suffix or '(none)'} (use .docx, .md or .txt)")
        rel, is_new = sc.add_notes(n)
        if is_new:
            added.append(rel)
    save(sc, dry_run)
    return AddResult(sidecar=sc, created=created, added_notes=added, warnings=warnings)


# -- link / unlink ------------------------------------------------------------
@dataclass
class LinkResult:
    sidecar: Sidecar
    link: Link
    action: str  # "added" | "extended" | "unchanged"
    bookmark_created: bool = False
    backup: Path | None = None
    section: Section | None = None


def pick(cands: list[Section], target: str, nth: int | None, notes_rel: str) -> Section:
    if not cands:
        raise UsageError(f'{notes_rel}: no heading or paragraph matches "{target}"',
                         fix=f"sn sections {shell_quote(notes_rel)}")
    if nth is not None:
        if not 1 <= nth <= len(cands):
            raise UsageError(f"--nth {nth}: only {len(cands)} matches for \"{target}\"")
        return cands[nth - 1]
    if len(cands) == 1:
        return cands[0]
    raise AmbiguousTarget(f'{notes_rel}: {len(cands)} sections match "{target}"; pick one with --nth N', cands)


def link(sc: Sidecar, slides_text: str, notes_arg: str | None, target: str | None, *, nth: int | None = None,
         page: int | None = None, dry_run: bool = False, confirm: Confirm | None = None) -> LinkResult:
    slides = SlideSet.parse(slides_text)
    slides.validate(sc.pages, sc.source_name)
    rel, path = resolve_notes(sc, notes_arg)
    require_file(path, "notes file")
    adapter = adapter_for(path)
    if page is not None:
        if path.suffix.lower() != ".docx":
            raise UsageError(f"{rel}: --page works only for Word (.docx) notes; link by heading text instead")
        section = adapter.section_on_page(page)  # type: ignore[attr-defined]
        if confirm is not None and not confirm(f'Page {page} starts with: "{short_label(section.label, 100)}". '
                                               "Bookmark this paragraph?"):
            raise UsageError("cancelled; nothing was changed")
    else:
        if not target:
            raise UsageError("missing TARGET (heading or paragraph text)", fix=f"sn sections {shell_quote(rel)}")
        section = pick(adapter.find(target), target, nth, rel)
    had_anchor = section.anchor is not None and (path.suffix.lower() != ".docx" or section.anchor.startswith("sn_"))
    anchor = adapter.ensure_anchor(section, dry_run=dry_run)
    label = short_label(section.label)
    existing = [l for l in sc.links if sc.same_notes(l.notes, rel) and l.anchor == anchor]
    if existing:
        row = existing[0]
        if slides.issubset(row.slides):
            action = "unchanged"
        else:
            row.slides = row.slides.union(slides)
            action = "extended"
        if not row.label:
            row.label = label
    else:
        row = Link(slides=slides, notes=rel, anchor=anchor, label=label)
        sc.links.append(row)
        action = "added"
    if action != "unchanged":
        save(sc, dry_run)
    elif not dry_run:
        lib_mod.register(sc)
    return LinkResult(sidecar=sc, link=row, action=action, bookmark_created=not had_anchor,
                      backup=getattr(adapter, "last_backup", None), section=section)


@dataclass
class UnlinkResult:
    sidecar: Sidecar
    removed: list[Link]
    shrunk: list[Link]
    purged: list[str]


def unlink(sc: Sidecar, slides_text: str, notes_arg: str | None, target: str, *, purge: bool = False,
           dry_run: bool = False) -> UnlinkResult:
    slides = SlideSet.parse(slides_text)
    rel, path = resolve_notes(sc, notes_arg)
    rows = [l for l in sc.links if sc.same_notes(l.notes, rel)]
    t = target.strip()
    anchors = {l.anchor for l in rows if l.anchor == t or l.label.casefold() == t.casefold()}
    if not anchors and path.exists():
        anchors = {s.anchor for s in adapter_for(path).find(t) if s.anchor}
    matching = [l for l in rows if l.anchor in anchors and set(l.slides) & set(slides)]
    if not matching:
        raise UsageError(f'{sc.source_name}: no link from slides {slides} to "{target}" in {rel}',
                         fix=f"sn map {shell_quote(display(sc.source_path))}")
    removed, shrunk = [], []
    for l in matching:
        rest = l.slides.difference(slides)
        if rest:
            l.slides = rest
            shrunk.append(l)
        else:
            sc.links.remove(l)
            removed.append(l)
    purged: list[str] = []
    if purge and path.suffix.lower() == ".docx" and path.exists():
        still_used = {l.anchor for l in sc.links if sc.same_notes(l.notes, rel)}
        still_used |= _anchors_used_elsewhere(sc, path)
        adapter = adapter_for(path)
        for l in removed:
            if l.anchor not in still_used and l.anchor.startswith("sn_") and l.anchor not in purged:
                if adapter.remove_bookmark(l.anchor, dry_run=dry_run):  # type: ignore[attr-defined]
                    purged.append(l.anchor)
    save(sc, dry_run)
    return UnlinkResult(sidecar=sc, removed=removed, shrunk=shrunk, purged=purged)


def _anchors_used_elsewhere(sc: Sidecar, notes_path: Path) -> set[str]:
    used: set[str] = set()
    for e in lib_mod.Library.load().entries:
        if same_path(e.sidecar, sc.path) or not e.sidecar.exists():
            continue
        try:
            other = sidecar_io.read(e.sidecar)
        except SnError:
            continue
        used |= {l.anchor for l in other.links if same_path(other.notes_path(l.notes), notes_path)}
    return used


# -- reading ------------------------------------------------------------------
def show(sc: Sidecar, slide: int, full: bool = False, max_lines: int = 20, pages: bool = True) -> dict[str, Any]:
    if slide < 1 or (sc.pages and slide > sc.pages):
        raise UsageError(f"{sc.source_name}: slide {slide} is out of range (1-{sc.pages})")
    groups: list[dict[str, Any]] = []
    by_notes: dict[str, dict[str, Any]] = {}
    adapters: dict[str, Any] = {}
    for l in sc.links_for(slide):
        path = sc.notes_path(l.notes)
        g = by_notes.get(l.notes)
        if g is None:
            g = {"notes": l.notes, "notes_path": str(path), "sections": []}
            by_notes[l.notes] = g
            groups.append(g)
        entry: dict[str, Any] = {"anchor": l.anchor, "label": l.label, "slides": l.slides.format(),
                                 "text": None, "lines": 0, "truncated": False, "page": None, "error": None}
        if not path.exists():
            entry["error"] = f"{l.notes}: notes file not found → run sn check --fix"
        else:
            if l.notes not in adapters:
                adapters[l.notes] = adapter_for(path)
            ad = adapters[l.notes]
            text = ad.extract(l.anchor)
            if text is None:
                entry["error"] = f"{l.notes}: anchor {l.anchor} not found (heading renamed?) → run sn check --fix"
            else:
                lines = text.split("\n")
                entry["lines"] = len(lines)
                if not full and len(lines) > max_lines:
                    text = "\n".join(lines[:max_lines])
                    entry["truncated"] = True
                entry["text"] = text
                if pages and hasattr(ad, "approx_page"):
                    from slidenotes.util.office import find_soffice
                    if find_soffice():
                        entry["page"] = ad.approx_page(l.anchor)
        g["sections"].append(entry)
    return {"source": sc.source_rel, "source_path": str(sc.source_path), "slide": slide, "groups": groups}


def slide_map(sc: Sidecar) -> dict[str, Any]:
    pages = sc.pages or max([l.slides.last for l in sc.links] + [0])
    rows = []
    for n in range(1, pages + 1):
        ls = sc.links_for(n)
        rows.append({"slide": n, "links": len(ls),
                     "sections": [{"notes": l.notes, "anchor": l.anchor, "label": l.label} for l in ls]})
    linked = sum(1 for r in rows if r["links"])
    return {"source": sc.source_rel, "pages": pages, "linked": linked, "unlinked": pages - linked, "slides": rows}


def sections(notes: Path, all: bool = False) -> list[Section]:
    notes = norm(notes)
    if not notes.exists():
        raise UsageError(f"{display(notes)}: notes file not found")
    return adapter_for(notes).sections(all=all)
