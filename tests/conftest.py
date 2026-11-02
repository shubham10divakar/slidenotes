from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from slidenotes.cli import app

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

SAMPLE_MD = """\
---
title: Word vectors
---

# Word vectors

Intro text.

## One-hot maths

Each word is a vector with a single 1.
Dimension equals vocabulary size.

```python
# not a heading
x = [0, 1, 0]
```

### Orthogonality

No notion of similarity: every pair is orthogonal.

## Word2Vec

Predict context words from a centre word.

## Negative sampling

Cheaper than a full softmax.
"""

SAMPLE_TXT = """\
Lecture notes, plain text.

# WordNet
A thesaurus of synonym sets.

# Distributional semantics
You shall know a word by the company it keeps.
## Context window
Words within a fixed window.

# Summary
Vectors beat taxonomies.
"""


def _p(text: str, style: str | None = None, bold: bool = False, extra: str = "") -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:p>{ppr}{extra}<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


DOCX_BODY = "".join([
    _p("CS224N Lecture 1", "Title"),
    _p("1 Introduction", "Heading1"),
    _p("Language is how we share knowledge."),
    _p("WordNet", bold=True),
    _p("WordNet is a thesaurus containing synonym sets."),
    _p("It misses nuance and new words."),
    _p("WordNet vs Word2Vec", bold=True),
    _p("Discrete symbols versus dense vectors."),
    _p("2 Representations", "Heading1"),
    _p("2.1 One-Hot Representation", "Heading2"),
    _p("A word is a vector with one 1 and many 0s."),
    '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>table cell text</w:t></w:r></w:p></w:tc></w:tr></w:tbl>',
    _p("2.2 Word2Vec", "Heading2"),
    _p("Predict context words.", extra='<w:bookmarkStart w:id="0" w:name="_GoBack"/><w:bookmarkEnd w:id="0"/>'),
    _p("3 Summary", "Heading1"),
    _p("Vectors capture meaning."),
])

DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    f'<w:document xmlns:w="{W_NS}" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="">'
    f'<w:body>{DOCX_BODY}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr></w:body></w:document>'
)

STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    f'<w:styles xmlns:w="{W_NS}">'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>'
    '<w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>'
    '</w:styles>'
)

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    '</Types>'
)

ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)

DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
    'Target="styles.xml"/></Relationships>'
)


def make_docx(path: Path, document_xml: str = DOCUMENT_XML) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/styles.xml", STYLES_XML)
        z.writestr("word/media/image1.png", b"\x89PNG\r\n\x1a\nfake-image-bytes")
    return path


def make_pdf(path: Path, pages: int = 10) -> Path:
    from pypdf import PdfWriter

    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        w.write(f)
    return path


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "sn-home"
    monkeypatch.setenv("SLIDENOTES_HOME", str(h))
    monkeypatch.setenv("SLIDENOTES_SOFFICE", str(tmp_path / "no-soffice"))  # never use a real LibreOffice
    return h


@pytest.fixture
def ws(tmp_path, home, monkeypatch) -> Path:
    """A study folder with sample.pdf (10 pages), sample.md, sample.txt, sample.docx."""
    d = tmp_path / "study"
    (d / "derivations").mkdir(parents=True)
    make_pdf(d / "sample.pdf", 10)
    (d / "sample.md").write_text(SAMPLE_MD, encoding="utf-8")
    (d / "derivations" / "vectors.md").write_text(SAMPLE_MD, encoding="utf-8")
    (d / "sample.txt").write_text(SAMPLE_TXT, encoding="utf-8")
    make_docx(d / "sample.docx")
    monkeypatch.chdir(d)
    return d


class Sn:
    def __init__(self):
        self.runner = CliRunner()

    def __call__(self, *args: str, code: int | None = 0, input: str | None = None):
        r = self.runner.invoke(app, list(args), input=input)
        if code is not None and r.exit_code != code:
            raise AssertionError(f"sn {' '.join(args)} exited {r.exit_code} (want {code})\n"
                                 f"stdout:\n{r.stdout}\nstderr:\n{getattr(r, 'stderr', '')}\n{r.exception!r}")
        return r


@pytest.fixture
def sn() -> Sn:
    os.environ.setdefault("COLUMNS", "200")
    return Sn()
