import pytest

from conftest import make_pdf

from slidenotes.errors import UsageError
from slidenotes.sources import source_for


def test_pdf_page_count_and_hash(tmp_path):
    p = make_pdf(tmp_path / "a.pdf", 7)
    s = source_for(p)
    assert s.page_count() == 7
    assert len(s.sha256()) == 64
    assert s.as_pdf() == p


def test_unsupported(tmp_path):
    with pytest.raises(UsageError):
        source_for(tmp_path / "a.key")


def test_pptx_fallback_counts_visible_slides(tmp_path, home, monkeypatch, sn):
    pptx = pytest.importorskip("pptx")
    prs = pptx.Presentation()
    for _ in range(5):
        prs.slides.add_slide(prs.slide_layouts[6])
    prs.slides[2]._element.set("show", "0")
    path = tmp_path / "deck.pptx"
    prs.save(path)
    s = source_for(path)
    assert s.page_count() == 4
    assert "hidden" in s.warnings[0]

    (tmp_path / "n.md").write_text("# Intro\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    r = sn("add", "deck.pptx", "--notes", "n.md")
    assert "4 pages" in r.stdout and "hidden" in r.stderr
    sn("link", "deck.pptx", "4", "Intro")
    sn("link", "deck.pptx", "5", "Intro", code=2)
