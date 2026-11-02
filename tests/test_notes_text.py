from slidenotes.notes import adapter_for
from slidenotes.notes.markdown import github_slug


def test_github_slug():
    assert github_slug("One-hot maths") == "one-hot-maths"
    assert github_slug("2.1 One-Hot Representation") == "21-one-hot-representation"
    assert github_slug("What's **new** in `v2`?") == "whats-new-in-v2"
    assert github_slug("snake_case stays") == "snake_case-stays"
    assert github_slug("Übung 3") == "übung-3"


def test_markdown_sections_skip_code_and_front_matter(ws):
    md = adapter_for(ws / "sample.md")
    labels = [(s.label, s.level, s.anchor) for s in md.sections()]
    assert labels == [
        ("Word vectors", 1, "word-vectors"),
        ("One-hot maths", 2, "one-hot-maths"),
        ("Orthogonality", 3, "orthogonality"),
        ("Word2Vec", 2, "word2vec"),
        ("Negative sampling", 2, "negative-sampling"),
    ]


def test_markdown_find_tiers(ws):
    md = adapter_for(ws / "sample.md")
    assert [s.anchor for s in md.find("One-hot maths")] == ["one-hot-maths"]
    assert [s.anchor for s in md.find("one-HOT maths")] == ["one-hot-maths"]
    assert [s.anchor for s in md.find("negative-sampling")] == ["negative-sampling"]
    # paragraph starting with the text -> enclosing section
    assert [s.anchor for s in md.find("Cheaper than")] == ["negative-sampling"]
    assert md.find("nothing like this") == []


def test_markdown_extract_extent(ws):
    md = adapter_for(ws / "sample.md")
    text = md.extract("one-hot-maths")
    assert text.startswith("## One-hot maths")
    assert "Orthogonality" in text          # deeper heading stays inside
    assert "Word2Vec" not in text           # same level ends it
    assert md.extract("orthogonality").strip().endswith("orthogonal.")
    assert md.extract("missing") is None


def test_duplicate_slugs(tmp_path):
    p = tmp_path / "d.md"
    p.write_text("# A\n## Notes\n## Notes\n## Notes\n", encoding="utf-8")
    assert [s.anchor for s in adapter_for(p).sections()] == ["a", "notes", "notes-1", "notes-2"]


def test_setext_headings(tmp_path):
    p = tmp_path / "s.md"
    p.write_text("Title\n=====\n\ntext\n\nPart two\n--------\nmore\n", encoding="utf-8")
    assert [(s.label, s.level) for s in adapter_for(p).sections()] == [("Title", 1), ("Part two", 2)]


def test_text_notes(ws):
    t = adapter_for(ws / "sample.txt")
    assert [(s.label, s.level) for s in t.sections()] == [
        ("WordNet", 1), ("Distributional semantics", 1), ("Context window", 2), ("Summary", 1)]
    text = t.extract("distributional-semantics")
    assert "Context window" in text and "Summary" not in text
    assert [s.anchor for s in t.find("wordnet")] == ["wordnet"]
