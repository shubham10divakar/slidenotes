"""`sn convert NOTES.docx`: one-time Word → Markdown via pandoc, rewriting sidecar rows."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from slidenotes.core import library as lib_mod
from slidenotes.core import sidecar as sidecar_io
from slidenotes.core.model import Sidecar
from slidenotes.errors import SnError, ToolMissing, UsageError
from slidenotes.notes.base import normalize, short_label
from slidenotes.notes.docx import DocxNotes
from slidenotes.notes.markdown import MarkdownNotes, strip_inline
from slidenotes.util.files import atomic_write_text, read_text
from slidenotes.util.office import find_pandoc
from slidenotes.util.paths import display, norm, same_path

_ANCHOR_SPAN = re.compile(r'<span id="[^"]*"(?: class="anchor")?></span>')
_ATX = re.compile(r"^(#{1,6})\s")


@dataclass
class ConvertResult:
    markdown: Path
    rewritten: list[str] = field(default_factory=list)   # "sidecar: anchor -> slug"
    promoted: list[str] = field(default_factory=list)    # bold paragraphs turned into headings
    unresolved: list[str] = field(default_factory=list)  # rows left pointing at the .docx
    sidecars: list[Path] = field(default_factory=list)


def _run_pandoc(docx: Path, out_dir: Path, out_name: str) -> Path:
    pandoc = find_pandoc()
    if not pandoc:
        raise ToolMissing(f"{display(docx)}: sn convert needs pandoc, which is not installed "
                          "(see https://pandoc.org/installing.html)")
    out = out_dir / out_name
    cmd = [pandoc, str(docx), "-f", "docx", "-t", "gfm", "--wrap=none", "--extract-media=assets", "-o", str(out)]
    try:
        subprocess.run(cmd, cwd=out_dir, check=True, capture_output=True, timeout=600)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        detail = getattr(e, "stderr", b"") or b""
        raise SnError(f"{display(docx)}: pandoc failed ({detail.decode(errors='replace').strip() or e})") from e
    return out


def _promote(lines: list[str], label: str) -> bool:
    """Turn a standalone line whose plain text equals `label` into a heading."""
    want = normalize(label).casefold()
    level = 2
    for i, line in enumerate(lines):
        m = _ATX.match(line)
        if m:
            level = min(len(m.group(1)) + 1, 6)
            continue
        plain = normalize(strip_inline(line.strip().strip("*_")))
        if plain and plain.casefold() == want:
            lines[i] = "#" * level + " " + plain
            return True
    return False


def _affected_sidecars(docx: Path) -> list[Sidecar]:
    paths: list[Path] = [e.sidecar for e in lib_mod.Library.load().entries if e.sidecar.exists()]
    paths += list(docx.parent.glob("*" + sidecar_io.SUFFIX))
    out: list[Sidecar] = []
    seen: list[Path] = []
    for p in paths:
        if any(same_path(p, s) for s in seen):
            continue
        seen.append(p)
        try:
            sc = sidecar_io.read(p)
        except SnError:
            continue
        if sc.find_notes_rel(docx) is not None or any(same_path(sc.notes_path(l.notes), docx) for l in sc.links):
            out.append(sc)
    return out


def convert(docx: Path, *, force: bool = False, dry_run: bool = False) -> ConvertResult:
    docx = norm(docx)
    if docx.suffix.lower() != ".docx":
        raise UsageError(f"{display(docx)}: sn convert takes a .docx file")
    if not docx.exists():
        raise UsageError(f"{display(docx)}: file not found")
    md_path = docx.with_suffix(".md")
    if md_path.exists() and not force:
        raise UsageError(f"{display(md_path)} already exists; pass --force to overwrite it")

    work = Path(tempfile.mkdtemp(prefix="slidenotes-convert-")) if dry_run else docx.parent
    try:
        out = _run_pandoc(docx, work, md_path.name)
        lines = _ANCHOR_SPAN.sub("", read_text(out)).split("\n")
        result = ConvertResult(markdown=md_path)
        word = DocxNotes(docx)
        sidecars = _affected_sidecars(docx)

        # First pass: make sure every linked section exists as a heading.
        wanted: dict[str, str] = {}
        for sc in sidecars:
            for l in sc.links:
                if same_path(sc.notes_path(l.notes), docx):
                    wanted[l.anchor] = word.label_for(l.anchor) or l.label
        md = MarkdownNotes(md_path)
        md._lines = lines
        for anchor, label in wanted.items():
            exact = [h for h in md.headings() if normalize(h.plain).casefold() == normalize(label).casefold()]
            if not exact and label and _promote(lines, label):
                result.promoted.append(short_label(label))
                md._headings = None
        text = "\n".join(lines)
        if not dry_run:
            atomic_write_text(md_path, text)
        md = MarkdownNotes(md_path)
        md._lines = text.split("\n")

        # Second pass: rewrite rows.
        for sc in sidecars:
            md_rel = sc.rel(md_path)
            docx_rel = sc.find_notes_rel(docx)
            left_on_docx = False
            for l in sc.links:
                if not same_path(sc.notes_path(l.notes), docx):
                    continue
                label = wanted.get(l.anchor) or l.label
                hits = [h for h in md.headings() if normalize(h.plain).casefold() == normalize(label).casefold()]
                if len(hits) >= 1:
                    old = l.anchor
                    l.notes, l.anchor, l.label = md_rel, hits[0].slug, short_label(hits[0].plain)
                    result.rewritten.append(f"{sc.path.name}: {old} → {md_rel}#{l.anchor}")
                else:
                    left_on_docx = True
                    result.unresolved.append(f"{sc.path.name}: {l.anchor} (\"{l.label}\") kept on {Path(l.notes).name}")
            if docx_rel is not None:
                notes = sc.notes
                if md_rel not in notes:
                    idx = notes.index(docx_rel)
                    notes.insert(idx + 1, md_rel)
                if not left_on_docx:
                    notes.remove(docx_rel)
                sc.meta["notes"] = notes
            result.sidecars.append(sc.path)
            if not dry_run:
                sidecar_io.write(sc)
                lib_mod.register(sc)
        return result
    finally:
        if dry_run:
            shutil.rmtree(work, ignore_errors=True)
