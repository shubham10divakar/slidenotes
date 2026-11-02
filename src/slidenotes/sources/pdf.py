from __future__ import annotations

from pathlib import Path

from slidenotes.errors import LockedError
from slidenotes.util.hashing import sha256_file
from slidenotes.util.paths import display


def pdf_page_count(path: Path) -> int:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            reader.decrypt("")
        return len(reader.pages)
    except FileNotFoundError:
        raise
    except (PdfReadError, OSError, ValueError, NotImplementedError) as e:
        raise LockedError(f"{display(path)}: cannot read PDF ({e})") from e
    except Exception as e:  # pypdf raises assorted errors on damaged or encrypted files
        raise LockedError(f"{display(path)}: cannot read PDF ({type(e).__name__}: {e})") from e


class PdfSource:
    def __init__(self, path: Path):
        self.path = path
        self.warnings: list[str] = []
        self._sha: str | None = None

    def page_count(self) -> int:
        return pdf_page_count(self.path)

    def sha256(self) -> str:
        if self._sha is None:
            self._sha = sha256_file(self.path)
        return self._sha

    def as_pdf(self) -> Path:
        return self.path
