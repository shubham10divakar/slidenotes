# SlideNotes — Feature List

*As of 2026-11-02*

Related: [DESIGN.md](DESIGN.md) · [ROADMAP.md](ROADMAP.md)

v0.1 ships 19 features, all terminal-based; search, the split-screen GUI and region anchors follow in v0.2 to v0.4.

## v0.1 (this release)

| # | Feature | Area |
| --- | --- | --- |
| F1 | Register a PDF source with one or more notes files | Library |
| F2 | Register PPT/PPTX sources (LibreOffice conversion, python-pptx fallback) | Sources |
| F3 | Sidecar `.links.md` next to each source, human-readable and hand-editable | Storage |
| F4 | Library file `~/.slidenotes/library.md` as the intro page | Storage |
| F5 | Slide sets: single, range, list (`3, 7, 10-12`) | Linking |
| F6 | n:n links across multiple notes files | Linking |
| F7 | Markdown notes: heading anchors with clickable `#slug` links | Notes |
| F8 | Text notes: `#` heading-line anchors | Notes |
| F9 | Word notes: automatic invisible bookmarks, text and formatting unchanged | Notes |
| F10 | `sn show`: print linked sections for a slide | Reading |
| F11 | `sn map`: slide-by-slide coverage, unlinked slides marked | Reading |
| F12 | `sn sections`: list linkable headings and bookmarks | Reading |
| F13 | `sn check`: detect missing files, changed sources, broken anchors | Integrity |
| F14 | `sn check --fix`: re-find moved files by hash, re-resolve renamed headings | Integrity |
| F15 | Safety: Word lock detection, one-time backup, atomic sidecar writes, `--dry-run` | Integrity |
| F16 | `sn open`: open source and notes in system apps | Reading |
| F17 | `sn convert`: one-time Word to Markdown with images extracted | Migration |
| F18 | `--json` output on read commands | Scripting |
| F19 | `sn link --page N` for Word notes (optional, needs LibreOffice; resolved once to a bookmark) | Linking |

## Later versions

| Version | Feature |
| --- | --- |
| v0.2 | `sn search "negative sampling"`: full-text search across all notes in the library, results grouped by source and slide |
| v0.2 | Cross-references between notes: `[[Concept]]` links, `sn backlinks Concept` |
| v0.2 | Screenshot importer: match images in an old .docx to PDF pages by perceptual hash, propose links, offer to remove the screenshots |
| v0.3 | Split-screen local app: `sn ui` opens slides (PDF.js) left, linked notes right, synced to the current slide |
| v0.3 | "Link to this slide" button and live Markdown + KaTeX preview |
| v0.4 | Region and highlight anchors on a slide (a box or a quote, not just a page) |
| v0.4 | Zotero integration: register papers from a Zotero library |
