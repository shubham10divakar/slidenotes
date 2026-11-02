"""Slide sets: `4`, `4-6`, `3, 7, 10-12`. Slides are 1-based."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Iterator

from slidenotes.errors import UsageError

_PART = re.compile(r"^\s*(\d+)\s*(?:[-–—]\s*(\d+)\s*)?$")
MAX_SLIDE = 100_000


class SlideSetError(UsageError):
    pass


@dataclass(frozen=True)
class SlideSet:
    slides: tuple[int, ...]

    @classmethod
    def parse(cls, text: str) -> "SlideSet":
        raw = str(text).strip()
        if not raw:
            raise SlideSetError("empty slide set (use e.g. 4, 4-6 or 3,7,10-12)")
        nums: set[int] = set()
        for part in raw.split(","):
            m = _PART.match(part)
            if not m:
                raise SlideSetError(f"invalid slide set {raw!r} (use e.g. 4, 4-6 or 3,7,10-12)")
            a = int(m.group(1))
            b = int(m.group(2)) if m.group(2) else a
            if a < 1:
                raise SlideSetError(f"invalid slide set {raw!r}: slides start at 1")
            if b < a:
                raise SlideSetError(f"invalid slide set {raw!r}: range {a}-{b} runs backwards")
            if b > MAX_SLIDE:
                raise SlideSetError(f"invalid slide set {raw!r}: slide {b} is too large")
            nums.update(range(a, b + 1))
        return cls(tuple(sorted(nums)))

    @classmethod
    def of(cls, slides: Iterable[int]) -> "SlideSet":
        return cls(tuple(sorted(set(slides))))

    def format(self) -> str:
        parts: list[str] = []
        s = self.slides
        i = 0
        while i < len(s):
            j = i
            while j + 1 < len(s) and s[j + 1] == s[j] + 1:
                j += 1
            parts.append(str(s[i]) if i == j else f"{s[i]}-{s[j]}")
            i = j + 1
        return ", ".join(parts)

    __str__ = format

    def __contains__(self, slide: object) -> bool:
        return slide in self.slides

    def __iter__(self) -> Iterator[int]:
        return iter(self.slides)

    def __len__(self) -> int:
        return len(self.slides)

    def __bool__(self) -> bool:
        return bool(self.slides)

    def contains(self, slide: int) -> bool:
        return slide in self.slides

    def expand(self) -> list[int]:
        return list(self.slides)

    @property
    def first(self) -> int:
        return self.slides[0] if self.slides else 0

    @property
    def last(self) -> int:
        return self.slides[-1] if self.slides else 0

    def union(self, other: "SlideSet") -> "SlideSet":
        return SlideSet.of(self.slides + other.slides)

    def difference(self, other: "SlideSet") -> "SlideSet":
        drop = set(other.slides)
        return SlideSet(tuple(n for n in self.slides if n not in drop))

    def issubset(self, other: "SlideSet") -> bool:
        return set(self.slides) <= set(other.slides)

    def out_of_range(self, pages: int) -> "SlideSet":
        return SlideSet(tuple(n for n in self.slides if n > pages))

    def validate(self, pages: int | None, source_name: str = "source") -> None:
        if pages is None:
            return
        bad = self.out_of_range(pages)
        if bad:
            what = "slide" if len(bad) == 1 else "slides"
            raise SlideSetError(f"{source_name}: {what} {bad} past the last page ({pages})")
