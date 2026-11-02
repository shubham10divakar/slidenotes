"""`sn check`: find broken links. `sn check --fix`: repair what can be repaired safely."""

from __future__ import annotations

import difflib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from slidenotes.core import library as lib_mod
from slidenotes.core import sidecar as sidecar_io
from slidenotes.core.model import Link, Sidecar
from slidenotes.errors import SnError
from slidenotes.notes import Section, adapter_for
from slidenotes.notes.base import normalize, short_label
from slidenotes.sources import source_for
from slidenotes.util.hashing import sha256_file
from slidenotes.util.paths import display, norm, shell_quote

Chooser = Callable[[str, list[str]], "int | None"]  # returns index or None to skip
Confirm = Callable[[str], bool]

AUTO_RATIO = 0.6
AUTO_MARGIN = 0.1
SEARCH_LIMIT = 50_000


@dataclass
class Problem:
    kind: str
    file: str
    message: str
    fix: str | None = None
    sidecar: str | None = None

    def __str__(self) -> str:
        return f"{self.message} → run {self.fix}" if self.fix else self.message

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "file": self.file, "message": self.message, "fix": self.fix,
                "sidecar": self.sidecar, "text": str(self)}


@dataclass
class FixReport:
    fixed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def check_sidecar(sc: Sidecar) -> list[Problem]:
    problems: list[Problem] = []
    scp = str(sc.path)
    src_q = shell_quote(display(sc.source_path))

    def add(kind: str, file: str, message: str, fix: str | None = "sn check --fix") -> None:
        problems.append(Problem(kind, file, message, fix, scp))

    src = sc.source_path
    pages = sc.pages
    if not src.exists():
        add("source_missing", sc.source_rel, f"{sc.source_rel}: source not found (moved or renamed?)")
    else:
        digest = sha256_file(src)
        if digest != sc.meta.get("source_sha256"):
            pages_note = ""
            try:
                new_pages = source_for(src).page_count()
                if sc.pages is not None and new_pages != sc.pages:
                    pages_note = f", pages {sc.pages} → {new_pages}"
                pages = new_pages
            except SnError:
                pass
            add("source_changed", sc.source_rel,
                f"{sc.source_name}: source changed since it was linked{pages_note}; slide numbers may have shifted "
                f"(review with sn map {src_q})", fix="sn check --fix --yes")
    for l in sc.links:
        if pages is not None:
            bad = l.slides.out_of_range(pages)
            if bad:
                add("slide_out_of_range", sc.source_rel,
                    f"{sc.source_name}: slides {bad} of \"{l.label or l.anchor}\" are past the last page ({pages})",
                    fix=f"sn unlink {src_q} {bad} {shell_quote(l.notes)} {shell_quote(l.anchor)}")
    adapters: dict[str, Any] = {}
    reported_missing: set[str] = set()
    for rel in sc.notes:
        if not sc.notes_path(rel).exists():
            add("notes_missing", rel, f"{rel}: notes file not found (moved or renamed?)")
            reported_missing.add(rel)
    for l in sc.links:
        if not any(sc.same_notes(l.notes, r) for r in sc.notes):
            add("notes_unregistered", l.notes, f"{l.notes}: used by a link but not listed under notes in "
                                                f"{sc.path.name}")
        path = sc.notes_path(l.notes)
        if not path.exists():
            if l.notes not in reported_missing:
                add("notes_missing", l.notes, f"{l.notes}: notes file not found (moved or renamed?)")
                reported_missing.add(l.notes)
            continue
        try:
            ad = adapters.get(l.notes) or adapters.setdefault(l.notes, adapter_for(path))
            if not ad.has_anchor(l.anchor):
                add("anchor_missing", l.notes, f"{l.notes}: anchor {l.anchor} not found (heading renamed?)")
        except SnError as e:
            add("notes_unreadable", l.notes, str(e), fix=None)
    return problems


def check_all(source: Path | None = None) -> tuple[list[Problem], list[Sidecar]]:
    """Check one sidecar (when `source` is given) or every sidecar in the library."""
    from slidenotes.core.service import load_sidecar

    if source is not None:
        sc = load_sidecar(source)
        return check_sidecar(sc), [sc]
    problems: list[Problem] = []
    sidecars: list[Sidecar] = []
    for e in lib_mod.Library.load().entries:
        if not e.sidecar.exists():
            problems.append(Problem("sidecar_missing", str(e.sidecar),
                                    f"{e.sidecar.name}: sidecar listed in the library no longer exists",
                                    "sn check --fix", str(e.sidecar)))
            continue
        try:
            sc = sidecar_io.read(e.sidecar)
        except SnError as err:
            problems.append(Problem("sidecar_invalid", str(e.sidecar), str(err), None, str(e.sidecar)))
            continue
        sidecars.append(sc)
        problems += check_sidecar(sc)
    return problems, sidecars


# -- fixing -------------------------------------------------------------------
def _search_roots(sc: Sidecar) -> list[Path]:
    roots = [sc.dir, sc.dir.parent]
    out: list[Path] = []
    for r in roots:
        r = norm(r)
        if r.is_dir() and r not in out:
            out.append(r)
    # Search the parent once, it covers the sidecar folder.
    return [out[-1]] if len(out) == 2 and out[0].is_relative_to(out[-1]) else out


def _walk_files(roots: list[Path]):
    seen = 0
    for root in roots:
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in lib_mod.SKIP_DIRS]
            for name in files:
                seen += 1
                if seen > SEARCH_LIMIT:
                    return
                yield Path(dirpath) / name


def find_by_hash(sc: Sidecar) -> list[Path]:
    want = sc.meta.get("source_sha256")
    suffix = Path(sc.source_rel).suffix.lower()
    hits = []
    for p in _walk_files(_search_roots(sc)):
        if p.suffix.lower() == suffix:
            try:
                if sha256_file(p) == want:
                    hits.append(p)
            except OSError:
                continue
    return hits


def find_by_name(sc: Sidecar, rel: str) -> list[Path]:
    name = Path(rel).name.casefold()
    return [p for p in _walk_files(_search_roots(sc)) if p.name.casefold() == name]


def _score(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a).casefold(), normalize(b).casefold()).ratio()


def _best(link: Link, cands: list[Section]) -> tuple[list[tuple[float, Section]], Section | None]:
    key = link.label or link.anchor.removeprefix("sn_").replace("_", " ").replace("-", " ")
    scored = sorted(((max(_score(key, s.label), _score(link.anchor, s.anchor or "")), s) for s in cands),
                    key=lambda x: -x[0])
    if scored and scored[0][0] >= AUTO_RATIO and (len(scored) == 1 or scored[0][0] - scored[1][0] >= AUTO_MARGIN):
        return scored, scored[0][1]
    return scored, None


def fix_sidecar(sc: Sidecar, problems: list[Problem], *, yes: bool = False, dry_run: bool = False,
                choose: Chooser | None = None, confirm: Confirm | None = None) -> FixReport:
    rep = FixReport()
    kinds = {p.kind for p in problems}

    if "source_missing" in kinds:
        hits = find_by_hash(sc)
        if len(hits) == 1:
            old = sc.source_rel
            sc.meta["source"] = sc.rel(hits[0])
            rep.fixed.append(f"{old}: found by hash at {sc.meta['source']}")
        else:
            rep.skipped.append(f"{sc.source_rel}: source not found by hash ({len(hits)} matches)")

    if "source_changed" in kinds:
        ok = yes or (confirm is not None and confirm(
            f"{sc.source_name} changed since it was linked. Accept the new version (keep all links)?"))
        if ok:
            ad = source_for(sc.source_path)
            sc.meta["source_sha256"] = ad.sha256()
            sc.meta["source_pages"] = ad.page_count()
            rep.fixed.append(f"{sc.source_name}: accepted new version ({sc.meta['source_pages']} pages)")
        else:
            rep.skipped.append(f"{sc.source_name}: source change not accepted (rerun with --yes to accept)")

    for p in problems:
        if p.kind != "notes_missing":
            continue
        rel = p.file
        hits = find_by_name(sc, rel)
        if len(hits) == 1:
            new_rel = sc.rel(hits[0])
            if rel not in sc.notes:
                sc.meta["notes"] = sc.notes + [rel]
            sc.replace_notes(rel, new_rel)
            rep.fixed.append(f"{rel}: found at {new_rel}")
        else:
            rep.skipped.append(f"{rel}: not found by name ({len(hits)} matches)")

    for p in problems:
        if p.kind == "notes_unregistered" and p.file not in sc.notes:
            sc.meta["notes"] = sc.notes + [p.file]
            rep.fixed.append(f"{p.file}: added to the notes list")

    # Anchors and labels (after files were re-found).
    adapters: dict[str, Any] = {}
    for l in sc.links:
        path = sc.notes_path(l.notes)
        if not path.exists():
            continue
        try:
            ad = adapters.get(l.notes) or adapters.setdefault(l.notes, adapter_for(path))
            if ad.has_anchor(l.anchor):
                fresh = ad.label_for(l.anchor)
                if fresh and fresh != l.label:
                    rep.fixed.append(f"{l.notes}: label \"{l.label}\" → \"{fresh}\"")
                    l.label = short_label(fresh)
                continue
            _fix_anchor(sc, l, ad, rep, dry_run=dry_run, choose=choose)
        except SnError as e:
            rep.skipped.append(str(e))

    if rep.fixed and not dry_run:
        sidecar_io.write(sc)
        lib_mod.register(sc)
    return rep


def _fix_anchor(sc: Sidecar, l: Link, ad: Any, rep: FixReport, *, dry_run: bool, choose: Chooser | None) -> None:
    is_docx = Path(l.notes).suffix.lower() == ".docx"
    cands = ad.sections(all=True)
    if is_docx and l.label:
        exact = [s for s in ad.find(l.label) if normalize(s.label).casefold() == normalize(l.label).casefold()]
        if len(exact) == 1:
            new = ad.ensure_anchor(exact[0], dry_run=dry_run)
            rep.fixed.append(f"{l.notes}: re-bookmarked \"{l.label}\" as {new}")
            l.anchor = new
            return
    scored, best = _best(l, cands)
    if best is None and choose is not None and scored:
        options = [f"{s.label}  ({s.anchor or 'new bookmark'}, {r:.0%})" for r, s in scored[:5]]
        idx = choose(f"{l.notes}: anchor {l.anchor} (\"{l.label}\") not found. Closest sections:", options)
        if idx is not None:
            best = scored[idx][1]
    if best is None:
        rep.skipped.append(f"{l.notes}: anchor {l.anchor} not found; no clear match "
                           f"(run sn sections {shell_quote(l.notes)} and relink)")
        return
    new = ad.ensure_anchor(best, dry_run=dry_run)
    rep.fixed.append(f"{l.notes}: {l.anchor} → {new} (\"{short_label(best.label)}\")")
    l.anchor = new
    l.label = short_label(best.label)


def fix_library(problems: list[Problem], dry_run: bool = False) -> FixReport:
    rep = FixReport()
    lib = lib_mod.Library.load()
    for p in problems:
        if p.kind == "sidecar_missing" and lib.remove(Path(p.file)):
            rep.fixed.append(f"{Path(p.file).name}: removed from the library")
    if rep.fixed and not dry_run:
        lib.save()
    return rep
