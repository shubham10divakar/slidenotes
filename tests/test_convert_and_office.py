import shutil

import pytest

from slidenotes.core import convert as convert_mod
from slidenotes.core import sidecar as io

FAKE_GFM = """\
# CS224N Lecture 1

# <span id="sn_intro" class="anchor"></span>1 Introduction

Language is how we share knowledge.

**WordNet**

WordNet is a thesaurus containing synonym sets.

# 2 Representations

## 2.1 One-Hot Representation

A word is a vector with one 1 and many 0s.

![](assets/media/image1.png)
"""


@pytest.fixture
def fake_pandoc(monkeypatch):
    def run(docx, out_dir, out_name):
        out = out_dir / out_name
        out.write_text(FAKE_GFM, encoding="utf-8")
        return out
    monkeypatch.setattr(convert_mod, "_run_pandoc", run)


def test_convert_rewrites_rows(ws, sn, fake_pandoc):
    (ws / "sample.md").unlink()
    sn("add", "sample.pdf", "--notes", "sample.docx")
    sn("link", "sample.pdf", "3", "WordNet")
    sn("link", "sample.pdf", "4-6", "2.1 One-Hot Representation")
    r = sn("convert", "sample.docx")
    assert "made heading: WordNet" in r.stdout
    md = (ws / "sample.md").read_text(encoding="utf-8")
    assert "<span" not in md
    assert "## WordNet" in md
    sc = io.read(ws / "sample.links.md")
    assert sc.notes == ["sample.md"]
    assert {(l.notes, l.anchor) for l in sc.links} == {("sample.md", "wordnet"),
                                                       ("sample.md", "21-one-hot-representation")}
    sn("check")
    assert (ws / "sample.docx").exists()
    sn("convert", "sample.docx", code=2)  # .md exists now


def test_convert_dry_run(ws, sn, fake_pandoc):
    (ws / "sample.md").unlink()
    sn("add", "sample.pdf", "--notes", "sample.docx")
    sn("link", "sample.pdf", "3", "WordNet")
    before = (ws / "sample.links.md").read_bytes()
    sn("convert", "sample.docx", "--dry-run")
    assert not (ws / "sample.md").exists()
    assert (ws / "sample.links.md").read_bytes() == before


def test_convert_without_pandoc(ws, sn, monkeypatch):
    (ws / "sample.md").unlink()
    monkeypatch.setenv("SLIDENOTES_PANDOC", "")
    monkeypatch.setattr(convert_mod, "find_pandoc", lambda: None)
    assert "pandoc" in sn("convert", "sample.docx", code=2).stderr


def test_page_without_libreoffice(ws, sn):
    sn("add", "sample.pdf", "--notes", "sample.docx")
    r = sn("link", "sample.pdf", "2", "sample.docx", "--page", "1", code=2)
    assert "LibreOffice" in r.stderr


def _real_soffice(monkeypatch):
    monkeypatch.delenv("SLIDENOTES_SOFFICE", raising=False)
    from slidenotes.util.office import find_soffice
    if not find_soffice():
        pytest.skip("LibreOffice not installed")


@pytest.mark.libreoffice
def test_page_with_libreoffice(ws, sn, monkeypatch):
    _real_soffice(monkeypatch)
    sn("add", "sample.pdf", "--notes", "sample.docx")
    r = sn("link", "sample.pdf", "2", "sample.docx", "--page", "1", "--yes")
    assert "CS224N Lecture 1" in r.stdout
    assert any(l.anchor == "sn_cs224n_lecture_1" for l in io.read(ws / "sample.links.md").links)


@pytest.mark.libreoffice
def test_pptx_via_libreoffice(tmp_path, home, sn, monkeypatch):
    _real_soffice(monkeypatch)
    pptx = pytest.importorskip("pptx")
    prs = pptx.Presentation()
    for _ in range(4):
        prs.slides.add_slide(prs.slide_layouts[6])
    prs.save(tmp_path / "deck.pptx")
    (tmp_path / "n.md").write_text("# A\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert "4 pages" in sn("add", "deck.pptx", "--notes", "n.md").stdout
    assert len(list((tmp_path / ".slidenotes" / "cache").glob("*.pdf"))) == 1
    shutil.rmtree(tmp_path / ".slidenotes")
