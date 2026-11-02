<div align="center">

# SlideNotes

**Link every slide to the notes that explain it. No screenshots.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Status](https://img.shields.io/badge/status-v0.1%20in%20development-orange.svg)

</div>

---

Your lecture notes are probably 90% pasted slide screenshots. One real set of notes weighs **10.6 MB for 2,600 words**, because of 14 screenshots, and none of those links between slide and explanation can be searched or checked.

SlideNotes replaces the screenshots with real links. Point any slide of a PDF or PowerPoint at any section of your Word, Markdown or text notes, and jump between them from your terminal.

```bash
sn add lecture1.pdf --notes lecture1.docx
sn link lecture1.pdf 4-6 "One-Hot Representation"
sn show lecture1.pdf 4
```

## Why SlideNotes

- **Many-to-many.** One slide → many sections across many files. One section → many slides.
- **Your files stay yours.** Slides are never modified. Word notes only gain invisible bookmarks.
- **Plain text all the way down.** Links live in a readable `.links.md` file next to your slides. Uninstall the tool and every link still works.
- **Links that don't rot.** Anchored to headings and bookmarks, not page numbers. `sn check` catches anything that breaks, and `sn check --fix` repairs it.
- **Use the editor you already like.** Word, VS Code, Obsidian, Notepad.

## Install

```bash
pip install slidenotes
```

> v0.1 is under active development and not on PyPI yet. Follow the [roadmap](v1/ROADMAP.md).

## Learn more

- [Guide](GUIDE.md): every command, option and file format
- [Design](v1/DESIGN.md) · [Features](v1/FEATURES.md) · [Roadmap](v1/ROADMAP.md)

<div align="center">
<sub>MIT licensed · Built by Subham Divakar</sub>
</div>
