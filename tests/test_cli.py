import json

from slidenotes.core import sidecar as io
from slidenotes.util import config


def test_phase1_gate_many_to_many(ws, sn):
    """Slide 4 links to three sections in two files; one section links to slides 3, 7 and 9."""
    sn("add", "sample.pdf", "--notes", "sample.md", "--notes", "sample.txt")
    sn("link", "sample.pdf", "4", "One-hot maths")
    sn("link", "sample.pdf", "4", "sample.md", "Word2Vec")
    sn("link", "sample.pdf", "4", "sample.txt", "WordNet")
    sn("link", "sample.pdf", "3,7,9", "sample.txt", "Summary")

    data = json.loads(sn("show", "sample.pdf", "4", "--json").stdout)
    got = {(g["notes"], s["anchor"]) for g in data["groups"] for s in g["sections"]}
    assert got == {("sample.md", "one-hot-maths"), ("sample.md", "word2vec"), ("sample.txt", "wordnet")}
    assert [g["notes"] for g in data["groups"]] == ["sample.md", "sample.txt"]

    for slide in (3, 7, 9):
        d = json.loads(sn("show", "sample.pdf", str(slide), "--json").stdout)
        assert [s["anchor"] for g in d["groups"] for s in g["sections"]] == ["summary"]
    assert json.loads(sn("show", "sample.pdf", "5", "--json").stdout)["groups"] == []

    sc = io.read(ws / "sample.links.md")
    summary = [l for l in sc.links if l.anchor == "summary"]
    assert len(summary) == 1 and summary[0].slides.format() == "3, 7, 9"

    raw = (ws / "sample.links.md").read_bytes()
    io.write(io.read(ws / "sample.links.md"))
    assert (ws / "sample.links.md").read_bytes() == raw


def test_linking_same_section_twice_merges_slides(ws, sn):
    sn("add", "sample.pdf", "--notes", "sample.md")
    sn("link", "sample.pdf", "3", "Word2Vec")
    sn("link", "sample.pdf", "7", "Word2Vec")
    r = sn("link", "sample.pdf", "7", "Word2Vec")
    assert "already linked" in r.stdout
    sc = io.read(ws / "sample.links.md")
    assert [(l.slides.format(), l.anchor) for l in sc.links] == [("3, 7", "word2vec")]


def test_sidecar_and_library_contents(ws, sn):
    sn("add", "sample.pdf", "--notes", "sample.md", "--notes", "derivations/vectors.md")
    sn("link", "sample.pdf", "4-6", "derivations/vectors.md", "One-hot maths")
    text = (ws / "sample.links.md").read_text(encoding="utf-8")
    assert "source: sample.pdf\n" in text
    assert "source_pages: 10\n" in text
    assert "  - derivations/vectors.md\n" in text
    assert "| 4-6 | [vectors.md](derivations/vectors.md#one-hot-maths) | one-hot-maths | One-hot maths |" in text
    lib = config.library_path().read_text(encoding="utf-8")
    assert "[sample.pdf](" in lib and "| 2 | 1 |" in lib


def test_docx_link_and_show(ws, sn):
    sn("add", "sample.pdf", "--notes", "sample.docx")
    r = sn("link", "sample.pdf", "3", "WordNet")
    assert "bookmark" in r.stdout
    sn("link", "sample.pdf", "4-6", "2.1 One-Hot Representation")
    d = json.loads(sn("show", "sample.pdf", "5", "--json").stdout)
    s = d["groups"][0]["sections"][0]
    assert s["anchor"] == "sn_2_1_one_hot_representation"
    assert s["text"].startswith("2.1 One-Hot Representation")
    text = (ws / "sample.links.md").read_text(encoding="utf-8")
    assert "| 3 | [sample.docx](sample.docx) | sn_wordnet | WordNet |" in text


def test_ambiguous_target_needs_nth(ws, sn):
    sn("add", "sample.pdf", "--notes", "sample.docx")
    r = sn("link", "sample.pdf", "2", "Word", code=2)
    assert "--nth" in r.stderr
    sn("link", "sample.pdf", "2", "Word", "--nth", "1")


def test_dry_run_writes_nothing(ws, sn):
    sn("add", "sample.pdf", "--notes", "sample.docx", "--dry-run")
    assert not (ws / "sample.links.md").exists()
    assert not config.library_path().exists()
    sn("add", "sample.pdf", "--notes", "sample.docx")
    before_sc = (ws / "sample.links.md").read_bytes()
    before_doc = (ws / "sample.docx").read_bytes()
    r = sn("link", "sample.pdf", "3", "WordNet", "--dry-run")
    assert "dry-run" in r.stdout
    assert (ws / "sample.links.md").read_bytes() == before_sc
    assert (ws / "sample.docx").read_bytes() == before_doc


def test_unlink_and_purge(ws, sn):
    sn("add", "sample.pdf", "--notes", "sample.docx")
    sn("link", "sample.pdf", "3,7", "WordNet")
    sn("unlink", "sample.pdf", "7", "WordNet")
    sc = io.read(ws / "sample.links.md")
    assert sc.links[0].slides.format() == "3"
    sn("unlink", "sample.pdf", "3", "sn_wordnet", "--purge")
    assert io.read(ws / "sample.links.md").links == []
    from slidenotes.notes.docx import DocxNotes
    assert not DocxNotes(ws / "sample.docx").has_anchor("sn_wordnet")
    sn("unlink", "sample.pdf", "3", "WordNet", code=2)


def test_map_marks_unlinked(ws, sn):
    sn("add", "sample.pdf", "--notes", "sample.md")
    sn("link", "sample.pdf", "1-2", "Word vectors")
    d = json.loads(sn("map", "sample.pdf", "--json").stdout)
    assert d["linked"] == 2 and d["unlinked"] == 8
    r = sn("map", "sample.pdf")
    assert "unlinked" in r.stdout


def test_sections_and_list(ws, sn):
    r = sn("sections", "sample.docx", "--all")
    assert "WordNet vs Word2Vec" in r.stdout
    d = json.loads(sn("sections", "sample.md", "--json").stdout)
    assert d[1]["anchor"] == "one-hot-maths"
    assert "empty" in sn("list").stdout
    sn("add", "sample.pdf", "--notes", "sample.md")
    d = json.loads(sn("list", "--json").stdout)
    assert d["sources"][0]["notes"] == 1 and d["sources"][0]["problems"] == []


def test_usage_errors(ws, sn):
    r = sn("show", "sample.pdf", "1", code=2)
    assert "not registered" in r.stderr and "sn add" in r.stderr
    sn("add", "sample.pdf", "--notes", "sample.md")
    assert "past the last page" in sn("link", "sample.pdf", "11", "Word2Vec", code=2).stderr
    assert "no heading" in sn("link", "sample.pdf", "1", "Nope nope", code=2).stderr
    assert "not a notes file" in sn("link", "sample.pdf", "1", "other.md", "X", code=2).stderr
    assert "unsupported" in sn("add", "sample.md", code=2).stderr
    sn("show", "sample.pdf", "11", code=2)


def test_add_rerun_adds_notes(ws, sn):
    sn("add", "sample.pdf", "--notes", "sample.md")
    r = sn("add", "sample.pdf", "--notes", "sample.md", "--notes", "sample.txt")
    assert "sample.txt" in r.stdout
    assert io.read(ws / "sample.links.md").notes == ["sample.md", "sample.txt"]


def test_library_rebuild(ws, sn):
    sn("add", "sample.pdf", "--notes", "sample.md")
    config.library_path().unlink()
    sn("library", "rebuild")
    d = json.loads(sn("list", "--json").stdout)
    assert len(d["sources"]) == 1


def test_version(sn):
    assert "0.1.0" in sn("--version").stdout
