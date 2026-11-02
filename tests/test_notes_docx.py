import re
import zipfile

import pytest
from lxml import etree

from slidenotes.errors import LockedError
from slidenotes.notes import adapter_for
from slidenotes.notes.docx import DocxNotes, bookmark_name

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def parts(path):
    with zipfile.ZipFile(path) as z:
        return {i.filename: z.read(i.filename) for i in z.infolist()}


def doc_text(path):
    root = etree.fromstring(parts(path)["word/document.xml"])
    return ["".join(t.text or "" for t in p.iter(W + "t")) for p in root.iter(W + "p")]


def strip_bookmarks(xml: bytes) -> bytes:
    return re.sub(rb"<w:bookmark(Start|End)[^>]*/>", b"", xml)


def test_sections_headings_and_bold(ws):
    d = adapter_for(ws / "sample.docx")
    heads = [(s.label, s.level) for s in d.sections()]
    assert heads == [("CS224N Lecture 1", 1), ("1 Introduction", 1), ("2 Representations", 1),
                     ("2.1 One-Hot Representation", 2), ("2.2 Word2Vec", 2), ("3 Summary", 1)]
    bold = [s.label for s in d.sections(all=True) if s.kind == "bold"]
    assert bold == ["WordNet", "WordNet vs Word2Vec"]


def test_find_prefers_bold_heading_over_paragraph(ws):
    d = adapter_for(ws / "sample.docx")
    hits = d.find("WordNet")
    assert [h.label for h in hits] == ["WordNet"]
    assert [h.label for h in d.find("wordnet is a")] == ["WordNet is a thesaurus containing synonym sets."]


def test_bookmark_insert_changes_only_bookmarks(ws):
    path = ws / "sample.docx"
    before = parts(path)
    text_before = doc_text(path)
    d = DocxNotes(path)
    sec = d.find("2.1 One-Hot Representation")[0]
    name = d.ensure_anchor(sec)
    assert name == "sn_2_1_one_hot_representation"
    after = parts(path)
    assert list(after) == list(before)  # same parts, same order
    for k in before:
        if k != "word/document.xml":
            assert after[k] == before[k], k
    new_xml = after["word/document.xml"]
    assert new_xml.startswith(b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n')
    assert b'<w:bookmarkStart w:id="1" w:name="sn_2_1_one_hot_representation"/>' in new_xml
    assert strip_bookmarks(new_xml) == strip_bookmarks(before["word/document.xml"])
    assert doc_text(path) == text_before
    # reload: bookmark found, rerun is a no-op
    d2 = DocxNotes(path)
    assert d2.has_anchor(name)
    assert d2.ensure_anchor(d2.find("2.1 One-Hot Representation")[0]) == name
    assert parts(path)["word/document.xml"] == new_xml


def test_backup_made_once(ws):
    path = ws / "sample.docx"
    original = path.read_bytes()
    d = DocxNotes(path)
    d.ensure_anchor(d.find("WordNet")[0])
    backup = ws / ".slidenotes" / "backup" / "sample.docx"
    assert backup.read_bytes() == original
    d = DocxNotes(path)
    d.ensure_anchor(d.find("3 Summary")[0])
    assert backup.read_bytes() == original


def test_lock_file_blocks_write(ws):
    path = ws / "sample.docx"
    (ws / "~$mple.docx").write_bytes(b"lock")
    before = path.read_bytes()
    d = DocxNotes(path)
    with pytest.raises(LockedError) as e:
        d.ensure_anchor(d.find("WordNet")[0])
    assert e.value.exit_code == 3
    assert path.read_bytes() == before


def test_extract_extents(ws):
    path = ws / "sample.docx"
    d = DocxNotes(path)
    h2 = d.ensure_anchor(d.find("2 Representations")[0])
    bold = d.ensure_anchor(DocxNotes(path).find("WordNet")[0])
    d = DocxNotes(path)
    text = d.extract(h2)
    assert text.split("\n")[0] == "2 Representations"
    assert "table cell text" in text and "2.2 Word2Vec" in text and "3 Summary" not in text
    # bold pseudo-heading runs to the next bold paragraph or heading
    assert d.extract(bold).split("\n") == ["WordNet", "WordNet is a thesaurus containing synonym sets.",
                                           "It misses nuance and new words."]


def test_remove_bookmark(ws):
    path = ws / "sample.docx"
    original = parts(path)["word/document.xml"]
    d = DocxNotes(path)
    name = d.ensure_anchor(d.find("3 Summary")[0])
    assert DocxNotes(path).remove_bookmark(name)
    assert parts(path)["word/document.xml"] == original


def test_bookmark_name_rules():
    assert bookmark_name("WordNet vs Word2Vec", set()) == "sn_wordnet_vs_word2vec"
    assert bookmark_name("WordNet", {"sn_wordnet"}) == "sn_wordnet_2"
    long = bookmark_name("A very long paragraph that keeps going well past forty characters", set())
    assert len(long) <= 40 and long.startswith("sn_") and not long.endswith("_")
    assert bookmark_name("∑∫", set()) == "sn_section"
