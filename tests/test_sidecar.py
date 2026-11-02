from pathlib import Path

import pytest

from slidenotes.core import sidecar as io
from slidenotes.core.model import Link
from slidenotes.core.slideset import SlideSet

GOLDEN = """\
---
slidenotes: 0.1
source: lecture1.pdf
source_sha256: 3f2a9c1e5b7d
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
| 4 | [word-vectors.md](../derivations/word-vectors.md#one-hot-maths) | one-hot-maths | One-hot maths |
| 4-6 | [lecture1.docx](lecture1.docx) | sn_one_hot | 2.1 One-Hot Representation |

My own remarks stay here.
"""


def test_golden_round_trip_is_byte_identical(tmp_path):
    p = tmp_path / "lecture1.links.md"
    p.write_bytes(GOLDEN.encode())
    sc = io.read(p)
    assert len(sc.links) == 4
    assert sc.notes == ["lecture1.docx", "../derivations/word-vectors.md"]
    assert sc.pages == 32
    io.write(sc)
    assert p.read_bytes() == GOLDEN.encode()


def test_parse_values(tmp_path):
    p = tmp_path / "lecture1.links.md"
    p.write_text(GOLDEN, encoding="utf-8")
    sc = io.read(p)
    md = [l for l in sc.links if l.anchor == "one-hot-maths"][0]
    assert md.notes == "../derivations/word-vectors.md"  # fragment stripped
    assert sc.links[1].slides.expand() == [3, 7]


def test_rows_sorted_and_free_text_kept(tmp_path):
    p = tmp_path / "deck.links.md"
    p.write_text(GOLDEN, encoding="utf-8")
    sc = io.read(p)
    sc.links.append(Link(SlideSet.parse("1"), "lecture1.docx", "sn_intro", "Intro"))
    io.write(sc)
    sc2 = io.read(p)
    assert [l.anchor for l in sc2.links][0] == "sn_intro"
    assert p.read_text(encoding="utf-8").endswith("My own remarks stay here.\n")


def test_hand_edits_tolerated(tmp_path):
    p = tmp_path / "x.links.md"
    p.write_bytes((
        "---\r\nsource: x.pdf\r\nnotes: [a.md]\r\n---\r\n\r\n"
        "|slides|notes|anchor|\r\n|:--|--|--|\r\n|3,7| a.md |intro|\r\n| 9 | [a b.md](<a b.md#x>) | x |\r\n"
    ).encode("utf-8"))
    sc = io.read(p)
    assert [l.slides.format() for l in sc.links] == ["3, 7", "9"]
    assert sc.links[1].notes == "a b.md"
    io.write(sc)
    again = io.read(p)
    assert [(l.notes, l.anchor) for l in again.links] == [("a.md", "intro"), ("a b.md", "x")]
    assert "(<a b.md#x>)" in p.read_text(encoding="utf-8")


def test_pipe_in_label_escaped(tmp_path):
    p = tmp_path / "y.links.md"
    sc = io.new_sidecar(tmp_path / "y.pdf", "abc", 3)
    sc.links.append(Link(SlideSet.parse("1"), "n.md", "a-b", "A | B"))
    io.write(sc)
    assert io.read(p).links[0].label == "A | B"


def test_bad_row_reports_line(tmp_path):
    p = tmp_path / "z.links.md"
    p.write_text("---\nsource: z.pdf\n---\n\n| Slides | Notes | Anchor | Label |\n|---|---|---|---|\n"
                 "| x | n.md | a | A |\n", encoding="utf-8")
    with pytest.raises(io.SidecarError, match=r"z.links.md:7"):
        io.read(p)


def test_missing_front_matter(tmp_path):
    p = tmp_path / "w.links.md"
    p.write_text("# nothing\n", encoding="utf-8")
    with pytest.raises(io.SidecarError, match="front matter"):
        io.read(p)


def test_new_sidecar_round_trip(tmp_path):
    sc = io.new_sidecar(Path(tmp_path / "deck.pdf"), "0123", 10)
    io.write(sc)
    first = sc.path.read_bytes()
    io.write(io.read(sc.path))
    assert sc.path.read_bytes() == first
    assert b"# Links: deck.pdf" in first
