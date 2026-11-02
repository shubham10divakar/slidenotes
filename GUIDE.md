# SlideNotes Guide

The full reference for SlideNotes v0.1: every command, option, file format and behaviour.

> Covers **slidenotes 0.1.0**. Design background: [v1/DESIGN.md](v1/DESIGN.md).

## Contents

1. [Install](#1-install)
2. [Concepts](#2-concepts)
3. [Quick start](#3-quick-start)
4. [Command reference](#4-command-reference)
5. [Global options](#5-global-options)
6. [Choosing a link target](#6-choosing-a-link-target)
7. [File formats](#7-file-formats)
8. [Notes formats and anchors](#8-notes-formats-and-anchors)
9. [Source formats](#9-source-formats)
10. [Safety](#10-safety)
11. [Errors and exit codes](#11-errors-and-exit-codes)
12. [Configuration](#12-configuration)
13. [Troubleshooting](#13-troubleshooting)
14. [Development](#14-development)

---

## 1. Install

```bash
pip install slidenotes            # core
pip install "slidenotes[ppt]"     # + python-pptx, for PPT slide counts without LibreOffice
```

Requires **Python 3.10+**. No server, no database, no account.

**Optional external tools**

| Tool | Enables | Without it |
| --- | --- | --- |
| LibreOffice (`soffice` on PATH) | PPT/PPTX → PDF conversion; `sn link --page N` on Word notes; approximate Word page in `sn show` | PPT slide count via python-pptx; `--page` refuses; no page hint |
| pandoc | `sn convert` (Word → Markdown) | `sn convert` refuses |

**From source (development)**

```bash
git clone https://github.com/shubham10divakar/slidenotes.git
cd slidenotes
pip install -e ".[dev]"
sn --help
```

---

## 2. Concepts

| Concept | What it is | Where it lives |
| --- | --- | --- |
| **Source** | The PDF, PPT or PPTX you study. Identified by path + SHA-256 of its bytes. | Anywhere; never modified |
| **Notes file** | A `.docx`, `.md` or `.txt` with your explanations. | Anywhere; stored relative to the sidecar |
| **Anchor** | A stable spot in a notes file: a Word bookmark, or a Markdown/text heading. | Inside the notes file |
| **Link** | One row joining a slide set to one anchor. | In the sidecar |
| **Sidecar** | `<source>.links.md`: header plus link table. | Next to the source |
| **Library** | `~/.slidenotes/library.md`: one row per sidecar. The intro page. | Your home folder |

**Many-to-many.** Each link is a row `(slides, notes file, anchor)`.

- Slide 4 explained by three sections → three rows that each contain 4.
- One section covering slides 3 and 7 → one row with slides `3, 7`.

**Slide numbers** are 1-based and match the page number your PDF viewer shows. For PPT/PPTX, slide N is page N of the converted PDF. Hidden slides are excluded, with a warning.

**Slide sets** accept:

| Form | Example | Means |
| --- | --- | --- |
| Single | `4` | slide 4 |
| Range | `4-6` | slides 4, 5, 6 |
| List | `3, 7, 10-12` | slides 3, 7, 10, 11, 12 |

On the command line, quote lists with spaces: `sn link deck.pdf "3, 7" ...` or write `3,7`.

---

## 3. Quick start

```bash
cd ~/study/cs224n

# 1. Register the slides with a notes file
sn add lecture1.pdf --notes lecture1.docx

# 2. See what you can link to
sn sections lecture1.docx

# 3. Link slides to sections
sn link lecture1.pdf 3 "WordNet"
sn link lecture1.pdf 3,7 "WordNet vs Word2Vec"
sn link lecture1.pdf 4-6 "2.1 One-Hot Representation"

# 4. Add a second notes file and link into it
sn add lecture1.pdf --notes ../derivations/word-vectors.md
sn link lecture1.pdf 4 word-vectors.md "One-hot maths"

# 5. Read
sn show lecture1.pdf 4      # two sections, from two files
sn map lecture1.pdf         # coverage of every slide
sn list                     # everything you've registered
```

---

## 4. Command reference

Every command that writes is safe to rerun and accepts `--dry-run`.

### `sn add` — register a source

```text
sn add SOURCE --notes FILE [--notes FILE ...] [--dry-run]
```

- Creates `SOURCE.links.md` next to the source if it doesn't exist.
- Hashes the source (SHA-256) and counts its pages.
- Records each notes file, path relative to the sidecar.
- Adds or updates the row in the library.
- **Rerun** to attach more notes files; existing ones are left as they are.
- For `.ppt`/`.pptx`, converts to PDF once and caches it (see [§9](#9-source-formats)).

```bash
sn add lecture1.pdf --notes lecture1.docx --notes extra.md
```

### `sn link` — link slides to a section

```text
sn link SOURCE SLIDES [NOTES] TARGET [--nth N] [--dry-run]
sn link SOURCE SLIDES NOTES.docx --page N [--dry-run]
```

| Argument | Meaning |
| --- | --- |
| `SOURCE` | A registered source |
| `SLIDES` | Slide set: `4`, `4-6`, `3,7,10-12` |
| `NOTES` | Which notes file. Optional; defaults to the first registered notes file. Name or path. |
| `TARGET` | Heading text or paragraph text to find (see [§6](#6-choosing-a-link-target)) |
| `--nth N` | When several sections match, pick match N without being asked |
| `--page N` | Word only; needs LibreOffice. Bookmark the first paragraph that starts on Word page N, after you confirm it. The page number is not stored. |

What it does:

- **Markdown / text:** resolves the heading to its slug; nothing is written to the notes file.
- **Word:** inserts an invisible bookmark `sn_<slug>` on the matched paragraph (after a one-time backup and a lock check).
- Adds a row to the sidecar, kept sorted by first slide, then notes file.
- Linking a section that already has a row **merges** the slides into that row: `sn link deck.pdf 3 X` then `sn link deck.pdf 7 X` gives one row `3, 7`.
- Rerunning the same link changes nothing.
- `--page` shows the paragraph it picked and asks before bookmarking; `--yes` skips the question (needed in scripts).

```bash
sn link lecture1.pdf 4-6 "2.1 One-Hot Representation"
sn link lecture1.pdf 4 word-vectors.md "One-hot maths"
sn link lecture1.pdf 9 lecture1.docx --page 3
```

### `sn unlink` — remove links

```text
sn unlink SOURCE SLIDES [NOTES] TARGET [--purge] [--dry-run]
```

- `TARGET` can be the anchor (`sn_wordnet`), the label, or heading text.
- Removes the given slides from matching rows: a row `3, 7` unlinked at `7` becomes `3`; a row left with no slides is deleted.
- Word bookmarks are **kept** by default (harmless, invisible, reusable).
- `--purge` also removes the bookmark when no row in any registered sidecar uses it.

### `sn show` — read the notes for a slide

```text
sn show SOURCE SLIDE [--full] [--json]
```

- Prints every section linked to `SLIDE`, grouped by notes file.
- Shows the first **20 lines** of each section; `--full` prints everything.
- With LibreOffice installed, Word sections show an approximate current page (`~p. 5`) for orientation only.

### `sn map` — slide-by-slide coverage

```text
sn map SOURCE [--json]
```

Lists every slide with its link count; slides with no links are marked so you can see the gaps.

### `sn sections` — list what you can link to

```text
sn sections NOTES [--all] [--json]
```

- Lists headings and existing `sn_` bookmarks in a notes file: the candidates for `TARGET`.
- `--all` also lists bold paragraphs in Word files (for notes whose "headings" are just bold text).

### `sn list` — the intro page

```text
sn list [--json]
```

Shows the library: every registered source, number of notes files, number of links, and warnings for broken links (runs a quick `check`).

### `sn check` — validate links

```text
sn check [SOURCE] [--fix] [--json]
```

Checks one sidecar, or all of them if `SOURCE` is omitted. Reports:

| Problem | Example |
| --- | --- |
| Missing source or notes file | moved or renamed |
| Source hash changed | the PDF was replaced by a new version, so slide numbers may have shifted |
| Anchor not found | heading renamed, bookmark deleted |
| Slide out of range | slide 40 in a 32-page deck |

Exit code `1` if anything is wrong. Also reported: notes used by a row but missing from the header, and library rows whose sidecar was deleted.

`--fix` repairs what it can:

- Re-finds a moved **source by hash** (searching the sidecar's folder and its parent).
- Re-finds moved **notes by file name** (same search; only when exactly one file matches).
- Refreshes labels from current heading text.
- Re-resolves renamed headings when exactly one candidate clearly matches. Otherwise it asks (in a terminal) or skips.
- Re-inserts a deleted Word bookmark when the paragraph text is still there.
- Accepts a **changed source** (new hash and page count) only after confirmation, or with `--yes`.
- Removes library rows whose sidecar no longer exists.

`--dry-run` shows the fixes without writing them.

### `sn open` — open in your apps

```text
sn open SOURCE [SLIDE] [--notes-only | --source-only]
```

- Opens the source in the system viewer, at `SLIDE` when a viewer that accepts a page is installed (SumatraPDF or Acrobat on Windows; zathura, evince or okular on Linux). Otherwise it opens normally and tells you the page.
- With `SLIDE`, opens every notes file linked to that slide; without it, the first notes file.
- PPT/PPTX open as the converted PDF when a cached conversion exists, else the deck itself.

### `sn library rebuild` — regenerate the library

```text
sn library rebuild [--dry-run]
```

```text
sn library rebuild [FOLDER ...] [--dry-run]
sn library path
```

The library is only a cache of the sidecars. `rebuild` rescans the folders of the sidecars already listed plus the given folders (default: the current folder), recursively, and rewrites `library.md`, so deleting it is safe. `path` prints where the library lives.

### `sn convert` — Word to Markdown, once

```text
sn convert NOTES.docx [--force] [--dry-run]
```

Needs pandoc. Converts the Word file to `NOTES.md` next to it (GitHub Markdown), extracts images to `assets/`, and rewrites the rows of every sidecar that links into it to point at the new headings.

- A linked **bold-text heading** becomes a real Markdown heading, one level below the heading above it.
- Rows that can't be matched stay on the `.docx`, with a warning.
- The original `.docx` is not changed or deleted. `--force` overwrites an existing `NOTES.md`.

---

## 5. Global options

| Option | On | Effect |
| --- | --- | --- |
| `--dry-run` | every writing command | Print what would change; write nothing |
| `--yes`, `-y` | `link`, `check` | Answer yes to confirmations (`--page`, accepting a changed source) |
| `--version`, `-V` | `sn` | Print the version |
| `--json` | `show`, `map`, `list`, `check`, `sections` | Machine-readable output, for scripts and the future GUI |
| `--help` | every command | Usage and options |

---

## 6. Choosing a link target

`TARGET` is matched in this order:

1. Exact heading text
2. Heading text, case-insensitive
3. A paragraph that starts with the text

If several sections match, the CLI lists them numbered and asks. In scripts, use `--nth N`.

Tip: run `sn sections NOTES` first and copy a heading from the output.

**Section extent** (what `sn show` prints):

- Markdown and Word headings: from the anchor to the next heading of the same or higher level.
- A bookmark on a plain or bold-text paragraph: to the next heading of any level, or the next bold-text heading.

A Word paragraph counts as a **bold-text heading** when all its text is bold and it is at most 150 characters.

**Why not Word page numbers?** A `.docx` stores no pages. Word recalculates them on every render, so they change with every edit and differ between machines. `--page N` is only a way to pick a paragraph once. The link itself is always the bookmark.

---

## 7. File formats

### Sidecar: `lecture1.links.md`

```markdown
---
slidenotes: 0.1
source: lecture1.pdf
source_sha256: 3f2a9c1e5b7d...
source_pages: 32
notes:
  - lecture1.docx
  - ../derivations/word-vectors.md
---

# Links: lecture1.pdf

| Slides | Notes | Anchor | Label |
|--------|-------|--------|-------|
| 3 | [lecture1.docx](lecture1.docx) | sn_wordnet | WordNet |
| 3, 7 | [lecture1.docx](lecture1.docx) | sn_wordnet_vs_w2v | WordNet vs Word2Vec |
| 4-6 | [lecture1.docx](lecture1.docx) | sn_one_hot | 2.1 One-Hot Representation |
| 4 | [word-vectors.md](../derivations/word-vectors.md#one-hot-maths) | one-hot-maths | One-hot maths |

My own remarks go here and are never touched.
```

Rules:

- Front matter is YAML; all paths are relative to the sidecar's folder.
- `Anchor` is the machine key. `Label` is for humans and is refreshed by `sn check --fix`.
- Markdown targets include `#anchor` so they jump in VS Code and Obsidian. Word targets link the file (Word can't jump to a bookmark from a URL).
- Rows are sorted by first slide, then notes file.
- Text below the table is preserved byte-for-byte.
- **Hand editing is fine.** Add or remove rows yourself, then run `sn check`.

### Library: `~/.slidenotes/library.md`

```markdown
# SlideNotes library

| Source | Notes | Links | Sidecar |
|--------|-------|-------|---------|
| [lecture1.pdf](/home/subham/study/cs224n/lecture1.pdf) | 2 | 12 | [lecture1.links.md](/home/subham/study/cs224n/lecture1.links.md) |
```

A cache that can always be regenerated with `sn library rebuild`.

### Working folders

| Path | Contents |
| --- | --- |
| `.slidenotes/backup/` (next to the notes) | One-time copy of each `.docx` before its first edit |
| `.slidenotes/cache/<sha256>.pdf` (next to the source) | Converted PDF for PPT/PPTX sources |

---

## 8. Notes formats and anchors

| Notes type | Anchor | Created by | Survives edits? |
| --- | --- | --- | --- |
| `.md` | GitHub-style heading slug: `## One-hot maths` → `one-hot-maths` | Already there; `sn link` resolves it | Yes, unless the heading is renamed |
| `.txt` | A line starting with `#`, treated as a heading | Already there | Yes, unless the line is renamed |
| `.docx` | Invisible bookmark `sn_<slug>` on the paragraph | Inserted by `sn link` | Yes; bookmarks move with their text |

**Word tips**

- Headings styled as *Heading 1/2/3* work best. Bold-text headings work too: use `sn sections --all`.
- Close the file in Word before `sn link`. SlideNotes detects Word's `~$` lock file and stops instead of writing.

---

## 9. Source formats

| Type | Page count | Notes |
| --- | --- | --- |
| `.pdf` | pypdf | Read-only, never modified |
| `.ppt` / `.pptx` | LibreOffice → cached PDF, or python-pptx fallback | Sidecar always records the original file; the cache rebuilds whenever the hash changes |

PPT conversion runs `soffice --headless --convert-to pdf` once and caches the result in `.slidenotes/cache/`.

---

## 10. Safety

- **Sources are never written.**
- **Word files** only ever gain bookmarks, added with targeted XML edits. Text and formatting are untouched.
- **One-time backup** of each `.docx` to `.slidenotes/backup/` before its first edit.
- **Lock detection:** refuses to write a `.docx` that is open in Word (exit code 3).
- **Atomic sidecar writes:** written to a temp file, then renamed, so a crash never leaves a half-written sidecar.
- **`--dry-run`** on everything that writes.

---

## 11. Errors and exit codes

Every error names the file, the problem and the command that fixes it:

```text
lecture1.docx: anchor sn_one_hot not found (heading renamed?) → run sn check --fix
```

| Code | Meaning |
| --- | --- |
| `0` | OK |
| `1` | Validation problems (from `sn check`) |
| `2` | Usage error (bad arguments, unknown source) |
| `3` | File locked or unreadable |

---

## 12. Configuration

| Variable | Default | Effect |
| --- | --- | --- |
| `SLIDENOTES_HOME` | `~/.slidenotes` | Where `library.md` lives |
| `SLIDENOTES_SOFFICE` | found on PATH or in the usual install folder | Path to LibreOffice's `soffice` |
| `SLIDENOTES_PANDOC` | found on PATH | Path to `pandoc` |

There is one global library. Per-folder filtering (`sn list cs224n`) may come later.

---

## 13. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `file is open in Word` / exit 3 | Close the document in Word and rerun |
| `sn sections` shows too few headings in a .docx | Your headings are bold text, not Heading styles: use `sn sections --all` |
| `anchor not found` | A heading was renamed: `sn check --fix` |
| `source hash changed` | The PDF was replaced. Review the links `sn check` lists; slide numbers may have shifted |
| `--page` refuses | Install LibreOffice, or link by heading/paragraph text |
| PPT pages look wrong | Hidden slides are excluded from numbering; check the warning from `sn add` |
| Library looks stale | `sn library rebuild` |

---

## 14. Development

### Layout

```text
src/slidenotes/
  cli.py              Typer commands, Rich output, --json
  core/               model, slideset, sidecar, library, check
  notes/              base, markdown, text, docx adapters
  sources/            base, pdf, ppt adapters
  util/               paths, hashing, config
tests/conftest.py     builds sample.pdf, .md, .txt, .docx (and .pptx) in a temp folder
```

The core knows only links and slide sets. Each notes and source format is an adapter (`NotesAdapter`, `SourceAdapter`), so adding a format never touches the core. Details: [v1/DESIGN.md §5](v1/DESIGN.md#5-architecture).

### Dependencies

`typer`, `rich`, `pypdf`, `lxml`, `pyyaml`. Optional: `python-pptx`, LibreOffice, pandoc.

Word files are read and edited directly with `lxml` (not python-docx), so only `word/document.xml` is ever re-serialised and every other part is copied as-is.

### Tests

```bash
pytest                    # LibreOffice tests skip themselves when soffice is missing
```

### Release

```bash
python -m build
twine check dist/*
twine upload dist/*
```

- Unit tests: slide-set parsing, sidecar round-trip, slug generation.
- Golden files for sidecar and library output.
- Word safety tests: text and all non-bookmark XML unchanged after linking.
- CI: Windows, macOS, Linux × Python 3.10–3.13. LibreOffice tests run on Linux only.

### Docs

| File | What |
| --- | --- |
| [v1/DESIGN.md](v1/DESIGN.md) | Full design: model, formats, CLI, architecture |
| [v1/FEATURES.md](v1/FEATURES.md) | v0.1 feature list (F1–F19) and later versions |
| [v1/ROADMAP.md](v1/ROADMAP.md) | Phased build plan, risks, decisions, testing |
