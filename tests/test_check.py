import json
import shutil

from conftest import make_pdf

from slidenotes.core import sidecar as io
from slidenotes.util import config


def setup(sn):
    sn("add", "sample.pdf", "--notes", "sample.md", "--notes", "sample.docx")
    sn("link", "sample.pdf", "4", "One-hot maths")
    sn("link", "sample.pdf", "3", "sample.docx", "WordNet")


def problems(sn, *args, code=1):
    return json.loads(sn("check", *args, "--json", code=code).stdout)


def test_clean(ws, sn):
    setup(sn)
    r = sn("check")
    assert "no problems" in r.stdout


def test_moved_source_refound_by_hash(ws, sn):
    setup(sn)
    (ws / "pdfs").mkdir()
    shutil.move(ws / "sample.pdf", ws / "pdfs" / "renamed.pdf")
    d = problems(sn, "sample.links.md")
    assert [p["kind"] for p in d["problems"]] == ["source_missing"]
    assert "sn check --fix" in d["problems"][0]["text"]
    sn("check", "sample.links.md", "--fix")
    assert io.read(ws / "sample.links.md").source_rel == "pdfs/renamed.pdf"


def test_moved_notes_refound(ws, sn):
    setup(sn)
    (ws / "notes").mkdir()
    shutil.move(ws / "sample.md", ws / "notes" / "sample.md")
    assert {p["kind"] for p in problems(sn)["problems"]} == {"notes_missing"}
    sn("check", "--fix")
    sc = io.read(ws / "sample.links.md")
    assert "notes/sample.md" in sc.notes
    assert [l.notes for l in sc.links if l.anchor == "one-hot-maths"] == ["notes/sample.md"]


def test_renamed_heading_reresolved(ws, sn):
    setup(sn)
    p = ws / "sample.md"
    p.write_text(p.read_text(encoding="utf-8").replace("## One-hot maths", "## One-hot mathematics"),
                 encoding="utf-8")
    d = problems(sn)
    assert d["problems"][0]["kind"] == "anchor_missing"
    assert "anchor one-hot-maths not found (heading renamed?) → run sn check --fix" in d["problems"][0]["text"]
    sn("check", "--fix")
    l = [l for l in io.read(ws / "sample.links.md").links if l.notes == "sample.md"][0]
    assert (l.anchor, l.label) == ("one-hot-mathematics", "One-hot mathematics")


def test_deleted_bookmark_reinserted(ws, sn):
    setup(sn)
    from slidenotes.notes.docx import DocxNotes
    DocxNotes(ws / "sample.docx").remove_bookmark("sn_wordnet")
    assert problems(sn)["problems"][0]["kind"] == "anchor_missing"
    sn("check", "--fix")
    assert DocxNotes(ws / "sample.docx").has_anchor("sn_wordnet")


def test_changed_source_and_out_of_range(ws, sn):
    setup(sn)
    sn("link", "sample.pdf", "9-10", "Word2Vec")
    make_pdf(ws / "sample.pdf", 8)
    kinds = sorted(p["kind"] for p in problems(sn)["problems"])
    assert kinds == ["slide_out_of_range", "source_changed"]
    msg = [p for p in problems(sn)["problems"] if p["kind"] == "source_changed"][0]["text"]
    assert "pages 10 → 8" in msg
    # without --yes the change is not accepted (non-interactive)
    sn("check", "--fix", code=1)
    sn("check", "--fix", "--yes", code=1)  # out-of-range remains
    kinds = [p["kind"] for p in problems(sn)["problems"]]
    assert kinds == ["slide_out_of_range"]
    assert io.read(ws / "sample.links.md").pages == 8


def test_label_refresh(ws, sn):
    setup(sn)
    sc = io.read(ws / "sample.links.md")
    sc.links[0].label = "stale"
    io.write(sc)
    r = sn("check", "--fix")
    assert "label" in r.stdout


def test_missing_sidecar_removed_from_library(ws, sn):
    setup(sn)
    (ws / "sample.links.md").unlink()
    assert problems(sn)["problems"][0]["kind"] == "sidecar_missing"
    sn("check", "--fix")
    assert "sample.links.md" not in config.library_path().read_text(encoding="utf-8")


def test_list_shows_warnings(ws, sn):
    setup(sn)
    (ws / "sample.md").unlink()
    r = sn("list")
    assert "problem" in r.stdout
    assert "notes file not found" in r.stderr
