"""PPT/PPTX: LibreOffice converts once to a cached PDF; python-pptx counts slides without it."""

from __future__ import annotations

from pathlib import Path

from slidenotes.errors import LockedError, ToolMissing
from slidenotes.sources.pdf import pdf_page_count
from slidenotes.util.hashing import sha256_file
from slidenotes.util.office import cached_pdf
from slidenotes.util.paths import display


class PptSource:
    def __init__(self, path: Path):
        self.path = path
        self.warnings: list[str] = []
        self._sha: str | None = None

    def sha256(self) -> str:
        if self._sha is None:
            self._sha = sha256_file(self.path)
        return self._sha

    def as_pdf(self, create: bool = True) -> Path | None:
        return cached_pdf(self.path, create=create)

    def _pptx_counts(self) -> tuple[int, int] | None:
        """(visible, hidden) slide counts via python-pptx, or None if it isn't installed."""
        if self.path.suffix.lower() != ".pptx":
            return None
        try:
            from pptx import Presentation
        except ImportError:
            return None
        try:
            prs = Presentation(str(self.path))
        except Exception as e:
            raise LockedError(f"{display(self.path)}: cannot read PowerPoint file ({e})") from e
        hidden = sum(1 for s in prs.slides if s._element.get("show") in ("0", "false"))
        return len(prs.slides) - hidden, hidden

    def page_count(self) -> int:
        counts = self._pptx_counts()
        if counts and counts[1]:
            what = "slide is" if counts[1] == 1 else "slides are"
            self.warnings.append(f"{display(self.path)}: {counts[1]} hidden {what} excluded from slide numbering")
        pdf = self.as_pdf()
        if pdf is not None:
            return pdf_page_count(pdf)
        if counts is not None:
            return counts[0]
        if self.path.suffix.lower() == ".ppt":
            raise ToolMissing(f"{display(self.path)}: .ppt files need LibreOffice (soffice) to count slides; "
                              "install LibreOffice or save the deck as .pptx")
        raise ToolMissing(f"{display(self.path)}: counting slides needs LibreOffice or python-pptx",
                          fix='pip install "slidenotes[ppt]"')
