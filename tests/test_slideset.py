import pytest

from slidenotes.core.slideset import SlideSet, SlideSetError


@pytest.mark.parametrize("text,expected", [
    ("4", [4]),
    ("4-6", [4, 5, 6]),
    ("3, 7, 10-12", [3, 7, 10, 11, 12]),
    ("3,7", [3, 7]),
    (" 7 , 3 ,3 ", [3, 7]),
    ("1–3", [1, 2, 3]),  # en dash
])
def test_parse(text, expected):
    assert SlideSet.parse(text).expand() == expected


@pytest.mark.parametrize("text", ["", "a", "0", "5-3", "3,,4", "-2", "1-", "4.5"])
def test_parse_rejects(text):
    with pytest.raises(SlideSetError):
        SlideSet.parse(text)


@pytest.mark.parametrize("slides,expected", [
    ([4], "4"), ([4, 5, 6], "4-6"), ([3, 7, 10, 11, 12], "3, 7, 10-12"), ([3, 4], "3-4"),
])
def test_format(slides, expected):
    assert SlideSet.of(slides).format() == expected


def test_round_trip():
    for text in ["4", "4-6", "3, 7, 10-12", "1, 3-5, 9"]:
        assert SlideSet.parse(text).format() == text


def test_contains_union_difference():
    s = SlideSet.parse("3, 7")
    assert 3 in s and 7 in s and 4 not in s
    assert s.union(SlideSet.parse("9")).format() == "3, 7, 9"
    assert SlideSet.parse("4-6").difference(SlideSet.parse("5")).format() == "4, 6"
    assert SlideSet.parse("4").issubset(SlideSet.parse("3-5"))


def test_validate_against_pages():
    SlideSet.parse("1-10").validate(10)
    with pytest.raises(SlideSetError, match="past the last page"):
        SlideSet.parse("9-11").validate(10)
