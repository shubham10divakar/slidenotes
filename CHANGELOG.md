# Changelog

## 0.1.0 — 2026-11-02

First release. Terminal-only; links are per slide/page.

**Linking**
- `sn add`: register a PDF, PPT or PPTX with one or more notes files (`.docx`, `.md`, `.txt`).
- `sn link`: link slide sets (`4`, `4-6`, `3, 7, 10-12`) to sections, many-to-many across files.
  Linking the same section again merges the slides into one row.
- `sn link --page N`: Word notes, with LibreOffice: bookmark the first paragraph on page N after confirmation.
- `sn unlink [--purge]`: remove slides from links; `--purge` also removes unused Word bookmarks.

**Notes formats**
- Markdown: GitHub-style heading slugs, clickable `file.md#slug` links in the sidecar.
- Text: lines starting with `#` are headings.
- Word: invisible `sn_<slug>` bookmarks inserted with targeted XML edits; text, formatting and every other
  part of the file stay unchanged. Bold-text headings are supported (`sn sections --all`).

**Reading**
- `sn show`, `sn map`, `sn sections`, `sn list`, `sn open`; `--json` on read commands.

**Integrity**
- `sn check`: missing files, changed sources, broken anchors, out-of-range slides (exit code 1).
- `sn check --fix`: re-find moved sources by hash and notes by name, refresh labels, re-resolve renamed headings.
- Word lock detection, one-time backups to `.slidenotes/backup/`, atomic sidecar writes, `--dry-run`.

**Migration**
- `sn convert`: one-time Word to Markdown via pandoc, images to `assets/`, sidecar rows moved to the new headings.
