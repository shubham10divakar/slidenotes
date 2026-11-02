"""The SourceAdapter interface: page count, hash, and a PDF to view."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from slidenotes.errors import UsageError
from slidenotes.util.paths import display

SUPPORTED_SUFFIXES = {".pdf", ".ppt", ".pptx"}


@runtime_checkable
class SourceAdapter(Protocol):
    path: Path
    warnings: list[str]

    def page_count(self) -> int: ...
    def sha256(self) -> str: ...
    def as_pdf(self) -> Path | None: ...  # identity for PDF, cached conversion for PPT (None if unavailable)


def source_for(path: Path) -> SourceAdapter:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from slidenotes.sources.pdf import PdfSource
        return PdfSource(path)
    if suffix in (".ppt", ".pptx"):
        from slidenotes.sources.ppt import PptSource
        return PptSource(path)
    raise UsageError(f"{display(path)}: unsupported source type {suffix or '(none)'} (use .pdf, .ppt or .pptx)")
