"""The `sn` command: Typer commands, Rich output, --json."""

from __future__ import annotations

import functools
import json
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from slidenotes import __version__
from slidenotes.core import check as check_mod
from slidenotes.core import library as lib_mod
from slidenotes.core import service
from slidenotes.core import sidecar as sidecar_io
from slidenotes.errors import EXIT_USAGE, EXIT_VALIDATION, AmbiguousTarget, SnError, UsageError
from slidenotes.notes.base import short_label
from slidenotes.util.paths import display, shell_quote

HELP = (
    "[bold]SlideNotes[/bold]: link every slide of a PDF or PowerPoint to the notes that explain it.\n\n"
    "Start with [cyan]sn add SOURCE --notes NOTES[/cyan], then [cyan]sn link SOURCE SLIDES TARGET[/cyan]."
)

app = typer.Typer(name="sn", help=HELP, no_args_is_help=True, add_completion=False, rich_markup_mode="rich",
                  context_settings={"help_option_names": ["-h", "--help"]})
library_app = typer.Typer(help="Manage the library file (~/.slidenotes/library.md).", no_args_is_help=True)
app.add_typer(library_app, name="library")

out = Console(highlight=False)
err = Console(stderr=True, highlight=False)

DryRun = typer.Option(False, "--dry-run", help="Print what would change; write nothing.")
Json = typer.Option(False, "--json", help="Machine-readable JSON output.")
Yes = typer.Option(False, "--yes", "-y", help="Answer yes to confirmations (for scripts).")


def _interactive() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def handle_errors(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except SnError as e:
            err.print(f"[red]error:[/red] {escape(str(e))}")
            raise typer.Exit(e.exit_code)
        except FileNotFoundError as e:
            err.print(f"[red]error:[/red] {escape(str(e.filename or e))}: file not found")
            raise typer.Exit(EXIT_USAGE)
        except PermissionError as e:
            err.print(f"[red]error:[/red] {escape(str(e.filename or e))}: permission denied (file open elsewhere?)")
            raise typer.Exit(3)
    return wrapper


def emit_json(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def dry(dry_run: bool) -> str:
    return "[yellow]\\[dry-run][/yellow] would have " if dry_run else ""


def warn(msg: str) -> None:
    err.print(f"[yellow]warning:[/yellow] {escape(msg)}")


def confirm_fn(yes: bool) -> Callable[[str], bool]:
    def confirm(question: str) -> bool:
        if yes:
            out.print(escape(question) + " [dim](--yes)[/dim]")
            return True
        if not _interactive():
            raise UsageError(f"{question} (needs confirmation; rerun with --yes)")
        return typer.confirm(question, default=False)
    return confirm


def choose_fn() -> Callable[[str, list[str]], Optional[int]] | None:
    if not _interactive():
        return None

    def choose(prompt: str, options: list[str]) -> Optional[int]:
        out.print(escape(prompt))
        for i, o in enumerate(options, 1):
            out.print(f"  [cyan]{i}[/cyan]  {escape(o)}")
        out.print("  [cyan]0[/cyan]  skip")
        n = typer.prompt("Choose", type=int, default=0)
        return n - 1 if 1 <= n <= len(options) else None
    return choose


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"slidenotes {__version__}")
        raise typer.Exit()


@app.callback()
def _root(version: bool = typer.Option(False, "--version", "-V", callback=version_callback, is_eager=True,
                                       help="Show the version and exit.")) -> None:
    pass


# -- add ------------------------------------------------------------------------
@app.command()
@handle_errors
def add(
    source: Path = typer.Argument(..., help="PDF, PPT or PPTX to study (never modified)."),
    notes: List[Path] = typer.Option([], "--notes", "-n", help="Notes file (.docx, .md, .txt). Repeatable."),
    dry_run: bool = DryRun,
) -> None:
    """Register a source with its notes files. Rerun to add more notes files."""
    r = service.add(source, notes, dry_run=dry_run)
    sc = r.sidecar
    for w in r.warnings:
        warn(w)
    verb = "created" if r.created else "updated"
    pages = f" ({sc.pages} pages)" if sc.pages is not None else ""
    out.print(f"{dry(dry_run)}{verb} [bold]{escape(sc.path.name)}[/bold] for {escape(sc.source_name)}{pages}")
    for rel in r.added_notes:
        out.print(f"  [green]+[/green] notes {escape(rel)}")
    if not r.added_notes and notes:
        out.print("  [dim]notes already registered; nothing new[/dim]")
    if r.created and not dry_run:
        first = r.added_notes[0] if r.added_notes else None
        hint = f"sn sections {shell_quote(first)}" if first else f"sn add {shell_quote(display(source))} --notes NOTES"
        out.print(f"[dim]next: {escape(hint)}[/dim]")


# -- link -------------------------------------------------------------------------
def _split_rest(rest: list[str], page: Optional[int]) -> tuple[Optional[str], Optional[str]]:
    if page is not None:
        if len(rest) > 1:
            raise UsageError("with --page give at most NOTES, not a TARGET")
        return (rest[0] if rest else None), None
    if not rest:
        raise UsageError("missing TARGET (heading or paragraph text to link to)")
    if len(rest) == 1:
        return None, rest[0]
    if len(rest) == 2:
        return rest[0], rest[1]
    raise UsageError("too many arguments; quote TARGET if it contains spaces, e.g. \"One-hot maths\"")


@app.command()
@handle_errors
def link(
    source: str = typer.Argument(..., help="A registered source (or its .links.md)."),
    slides: str = typer.Argument(..., help="Slide set: 4, 4-6 or 3,7,10-12."),
    rest: Optional[List[str]] = typer.Argument(None, metavar="[NOTES] TARGET",
                                               help="Optional notes file (default: the first), then heading or "
                                                    "paragraph text."),
    page: Optional[int] = typer.Option(None, "--page", help="Word only, needs LibreOffice: bookmark the first "
                                                            "paragraph on Word page N."),
    nth: Optional[int] = typer.Option(None, "--nth", help="Pick match N when several sections match."),
    yes: bool = Yes,
    dry_run: bool = DryRun,
) -> None:
    """Link a slide set to a section of a notes file. Word files get an invisible bookmark."""
    notes_arg, target = _split_rest(list(rest or []), page)
    sc = service.load_sidecar(source)
    try:
        r = service.link(sc, slides, notes_arg, target, nth=nth, page=page, dry_run=dry_run,
                         confirm=confirm_fn(yes))
    except AmbiguousTarget as e:
        chooser = choose_fn()
        if chooser is None:
            err.print(f"[red]error:[/red] {escape(e.message)}")
            for i, s in enumerate(e.candidates, 1):
                err.print(f"  {i}  {escape(short_label(s.label, 90))}  [dim]({s.kind})[/dim]")
            raise typer.Exit(EXIT_USAGE)
        idx = chooser(e.message.split(";")[0] + ":", [f"{short_label(s.label, 90)}  ({s.kind})" for s in e.candidates])
        if idx is None:
            raise typer.Exit(EXIT_USAGE)
        sc = service.load_sidecar(source)
        r = service.link(sc, slides, notes_arg, target, nth=idx + 1, dry_run=dry_run, confirm=confirm_fn(yes))
    l = r.link
    verb = {"added": "linked", "extended": "extended", "unchanged": "already linked"}[r.action]
    prefix = dry(dry_run) if r.action != "unchanged" else ""
    out.print(f"{prefix}{verb} slides [bold]{l.slides}[/bold] → {escape(Path(l.notes).name)} › "
              f"[cyan]{escape(l.label)}[/cyan] [dim]({escape(l.anchor)})[/dim]")
    if r.bookmark_created and Path(l.notes).suffix.lower() == ".docx":
        out.print(f"  {dry(dry_run)}{'added' if not dry_run else 'add'} bookmark [cyan]{escape(l.anchor)}[/cyan]")
    if r.backup:
        out.print(f"  [dim]backup of the original saved to {escape(display(r.backup))}[/dim]")


@app.command()
@handle_errors
def unlink(
    source: str = typer.Argument(..., help="A registered source."),
    slides: str = typer.Argument(..., help="Slides to unlink: 4, 4-6, 3,7."),
    rest: List[str] = typer.Argument(..., metavar="[NOTES] TARGET", help="Optional notes file, then the "
                                                                          "anchor, label or heading text."),
    purge: bool = typer.Option(False, "--purge", help="Also remove the Word bookmark when nothing uses it."),
    dry_run: bool = DryRun,
) -> None:
    """Remove links. Word bookmarks stay unless --purge."""
    notes_arg, target = _split_rest(list(rest), None)
    assert target is not None
    sc = service.load_sidecar(source)
    r = service.unlink(sc, slides, notes_arg, target, purge=purge, dry_run=dry_run)
    for l in r.removed:
        out.print(f"{dry(dry_run)}removed [bold]{escape(l.label or l.anchor)}[/bold] ({escape(Path(l.notes).name)})")
    for l in r.shrunk:
        out.print(f"{dry(dry_run)}narrowed [bold]{escape(l.label or l.anchor)}[/bold] to slides {l.slides}")
    for a in r.purged:
        out.print(f"{dry(dry_run)}removed bookmark [cyan]{escape(a)}[/cyan]")


# -- reading ----------------------------------------------------------------------
@app.command()
@handle_errors
def show(
    source: str = typer.Argument(..., help="A registered source."),
    slide: int = typer.Argument(..., help="Slide number (1-based)."),
    full: bool = typer.Option(False, "--full", help="Print whole sections (default: first 20 lines)."),
    as_json: bool = Json,
) -> None:
    """Print every notes section linked to a slide, grouped by notes file."""
    sc = service.load_sidecar(source)
    data = service.show(sc, slide, full=full)
    if as_json:
        emit_json(data)
        return
    out.rule(f"[bold]{escape(sc.source_name)}[/bold] · slide {slide}")
    if not data["groups"]:
        out.print(f"[dim]No notes linked to slide {slide}.[/dim]")
        out.print(f"[dim]link one: sn link {escape(shell_quote(display(sc.source_path)))} {slide} \"Heading\"[/dim]")
        return
    for g in data["groups"]:
        out.print()
        out.print(f"[bold magenta]{escape(Path(g['notes']).name)}[/bold magenta]  [dim]{escape(g['notes'])}[/dim]")
        for s in g["sections"]:
            meta = [f"slides {s['slides']}", s["anchor"]]
            if s["page"]:
                meta.append(f"~p. {s['page']}")
            out.print(f"\n[bold cyan]▌ {escape(s['label'] or s['anchor'])}[/bold cyan]  "
                      f"[dim]{escape(' · '.join(meta))}[/dim]")
            if s["error"]:
                out.print(f"  [red]{escape(s['error'])}[/red]")
                continue
            for line in s["text"].split("\n"):
                out.print("  " + escape(line), soft_wrap=True)
            if s["truncated"]:
                out.print(f"  [dim]… {s['lines'] - 20} more lines (--full)[/dim]")


@app.command("map")
@handle_errors
def map_cmd(
    source: str = typer.Argument(..., help="A registered source."),
    as_json: bool = Json,
) -> None:
    """Slide-by-slide coverage: link counts, unlinked slides marked."""
    sc = service.load_sidecar(source)
    data = service.slide_map(sc)
    if as_json:
        emit_json(data)
        return
    t = Table(title=f"{escape(sc.source_name)}: {data['linked']}/{data['pages']} slides linked",
              title_justify="left", header_style="bold")
    t.add_column("Slide", justify="right")
    t.add_column("Links", justify="right")
    t.add_column("Sections")
    for r in data["slides"]:
        if r["links"]:
            secs = "\n".join(f"{escape(s['label'] or s['anchor'])} [dim]({escape(Path(s['notes']).name)})[/dim]"
                             for s in r["sections"])
            t.add_row(str(r["slide"]), str(r["links"]), secs)
        else:
            t.add_row(f"[red]{r['slide']}[/red]", "[red]0[/red]", "[red dim]— unlinked[/red dim]")
    out.print(t)


@app.command()
@handle_errors
def sections(
    notes: Path = typer.Argument(..., help="A notes file (.docx, .md, .txt)."),
    all_: bool = typer.Option(False, "--all", help="Word: also list bold paragraphs (bold-text headings)."),
    as_json: bool = Json,
) -> None:
    """List headings and bookmarks in a notes file: the candidates for TARGET."""
    secs = service.sections(notes, all=all_)
    if as_json:
        emit_json([s.to_dict() for s in secs])
        return
    if not secs:
        hint = " (try --all for bold-text headings)" if notes.suffix.lower() == ".docx" and not all_ else ""
        out.print(f"[dim]No headings found in {escape(notes.name)}{escape(hint)}.[/dim]")
        return
    t = Table(header_style="bold", title=escape(notes.name), title_justify="left")
    t.add_column("Section")
    t.add_column("Kind", style="dim")
    t.add_column("Anchor", style="cyan")
    for s in secs:
        indent = "  " * max(s.level - 1, 0)
        t.add_row(indent + escape(short_label(s.label, 90)), s.kind if not s.level else f"h{s.level}",
                  escape(s.anchor or ""))
    out.print(t)
    if notes.suffix.lower() == ".docx" and not all_:
        out.print("[dim]tip: --all also lists bold paragraphs[/dim]")


@app.command("list")
@handle_errors
def list_cmd(as_json: bool = Json) -> None:
    """The intro page: every registered source with link counts and broken-link warnings."""
    lib = lib_mod.Library.load()
    rows = []
    for e in lib.entries:
        status: list[str] = []
        if not e.sidecar.exists():
            status = [f"{e.sidecar.name}: sidecar missing → run sn check --fix"]
            notes, links = e.notes, e.links
        else:
            try:
                sc = sidecar_io.read(e.sidecar)
                notes, links = len(sc.notes), len(sc.links)
                status = [str(p) for p in check_mod.check_sidecar(sc)]
            except SnError as ex:
                notes, links = e.notes, e.links
                status = [str(ex)]
        rows.append({**e.to_dict(), "notes": notes, "links": links, "problems": status})
    if as_json:
        emit_json({"library": str(lib.path), "sources": rows})
        return
    if not rows:
        out.print("[dim]The library is empty.[/dim]")
        out.print("[dim]start: sn add SOURCE --notes NOTES[/dim]")
        return
    t = Table(title="SlideNotes library", title_justify="left", header_style="bold")
    t.add_column("Source", style="bold")
    t.add_column("Notes", justify="right")
    t.add_column("Links", justify="right")
    t.add_column("Status")
    t.add_column("Folder", style="dim")
    for r in rows:
        status = "[green]ok[/green]" if not r["problems"] else f"[yellow]{len(r['problems'])} problem(s)[/yellow]"
        t.add_row(escape(Path(r["source"]).name), str(r["notes"]), str(r["links"]), status,
                  escape(display(Path(r["sidecar"]).parent)))
    out.print(t)
    for r in rows:
        for p in r["problems"]:
            warn(p)


@app.command()
@handle_errors
def check(
    source: Optional[str] = typer.Argument(None, help="Check one source (default: every source in the library)."),
    fix: bool = typer.Option(False, "--fix", help="Re-find moved files, refresh labels, re-resolve renamed headings."),
    yes: bool = Yes,
    dry_run: bool = DryRun,
    as_json: bool = Json,
) -> None:
    """Validate sidecars. Exit code 1 when problems remain."""
    problems, sidecars = check_mod.check_all(Path(source) if source else None)
    fixed: list[str] = []
    skipped: list[str] = []
    if fix:
        for sc in sidecars:
            mine = [p for p in problems if p.sidecar == str(sc.path)]
            rep = check_mod.fix_sidecar(sc, mine, yes=yes, dry_run=dry_run, choose=None if as_json else choose_fn(),
                                        confirm=confirm_fn(yes) if (yes or _interactive()) else None)
            fixed += rep.fixed
            skipped += rep.skipped
        if source is None:
            fixed += check_mod.fix_library(problems, dry_run=dry_run).fixed
        if not dry_run:
            problems, _ = check_mod.check_all(Path(source) if source else None)
    if as_json:
        emit_json({"problems": [p.to_dict() for p in problems], "fixed": fixed, "skipped": skipped,
                   "checked": [str(sc.path) for sc in sidecars]})
    else:
        for f in fixed:
            out.print(f"{dry(dry_run)}[green]fixed[/green] {escape(f)}")
        for s in skipped:
            out.print(f"[yellow]skipped[/yellow] {escape(s)}")
        for p in problems:
            err.print(f"[red]✗[/red] {escape(str(p))}")
        n = len(sidecars)
        if not problems:
            out.print(f"[green]✓[/green] {n} sidecar{'s' if n != 1 else ''} checked, no problems")
        else:
            out.print(f"{len(problems)} problem{'s' if len(problems) != 1 else ''} in {n} "
                      f"sidecar{'s' if n != 1 else ''}")
    if problems:
        raise typer.Exit(EXIT_VALIDATION)


@app.command("open")
@handle_errors
def open_cmd(
    source: str = typer.Argument(..., help="A registered source."),
    slide: Optional[int] = typer.Argument(None, help="Slide to open at (where the viewer supports it)."),
    notes_only: bool = typer.Option(False, "--notes-only", help="Open only the notes."),
    source_only: bool = typer.Option(False, "--source-only", help="Open only the source."),
) -> None:
    """Open the source in the system viewer and its notes in their default apps."""
    from slidenotes.util.opener import open_default, open_pdf_at

    sc = service.load_sidecar(source)
    service.require_file(sc.source_path, "source")
    if not notes_only:
        path = sc.source_path
        if path.suffix.lower() != ".pdf":
            from slidenotes.sources.ppt import PptSource
            pdf = PptSource(path).as_pdf(create=False) if slide else None
            if pdf is not None:
                path = pdf
        if path.suffix.lower() == ".pdf":
            at_page = open_pdf_at(path, slide)
            if slide and not at_page:
                out.print(f"[dim]opened {escape(path.name)}; go to page {slide} (your viewer can't be told the page)"
                          "[/dim]")
        else:
            open_default(path)
        out.print(f"opened {escape(sc.source_name)}" + (f" at slide {slide}" if slide else ""))
    if not source_only:
        rels = list(dict.fromkeys(l.notes for l in sc.links_for(slide))) if slide else sc.notes[:1]
        if slide and not rels:
            out.print(f"[dim]no notes linked to slide {slide}[/dim]")
        for rel in rels:
            p = sc.notes_path(rel)
            service.require_file(p, "notes file")
            open_default(p)
            out.print(f"opened {escape(rel)}")


@library_app.command("rebuild")
@handle_errors
def library_rebuild(
    folders: Optional[List[Path]] = typer.Argument(None, help="Extra folders to scan (default: the current folder)."),
    dry_run: bool = DryRun,
) -> None:
    """Regenerate library.md from the sidecars it can find."""
    lib, warnings = lib_mod.rebuild(list(folders) if folders else [Path.cwd()])
    for w in warnings:
        warn(w)
    if not dry_run:
        lib.save()
    out.print(f"{dry(dry_run)}rebuilt {escape(display(lib.path))}: {len(lib.entries)} source(s)")


@library_app.command("path")
def library_path() -> None:
    """Print where library.md lives."""
    typer.echo(str(lib_mod.Library.load().path))


@app.command()
@handle_errors
def convert(
    notes: Path = typer.Argument(..., help="The .docx to convert."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing .md of the same name."),
    dry_run: bool = DryRun,
) -> None:
    """One-time Word to Markdown via pandoc; images go to assets/, sidecar rows move to the new headings."""
    from slidenotes.core.convert import convert as do_convert

    r = do_convert(notes, force=force, dry_run=dry_run)
    out.print(f"{dry(dry_run)}written {escape(display(r.markdown))}")
    for p in r.promoted:
        out.print(f"  {dry(dry_run)}made heading: {escape(p)}")
    for line in r.rewritten:
        out.print(f"  {dry(dry_run)}moved {escape(line)}")
    for line in r.unresolved:
        warn(line)
    out.print(f"[dim]{escape(notes.name)} itself was not changed[/dim]")


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or "").lower().replace("-", "") != "utf8":
                stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    app()


if __name__ == "__main__":
    main()
