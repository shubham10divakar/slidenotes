"""Optional external tools: LibreOffice (soffice) and pandoc."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from slidenotes.errors import SnError, ToolMissing
from slidenotes.util.config import work_dir
from slidenotes.util.hashing import sha256_file

_SOFFICE_CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


def find_soffice() -> str | None:
    env = os.environ.get("SLIDENOTES_SOFFICE")
    if env:
        return env if Path(env).exists() else None
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for cand in _SOFFICE_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None


def find_pandoc() -> str | None:
    return os.environ.get("SLIDENOTES_PANDOC") or shutil.which("pandoc")


def convert_to_pdf(src: Path, timeout: int = 300) -> Path:
    """Convert with LibreOffice into a temp folder; returns the PDF path (caller moves it)."""
    soffice = find_soffice()
    if not soffice:
        raise ToolMissing(f"{src.name}: LibreOffice (soffice) is not installed")
    outdir = Path(tempfile.mkdtemp(prefix="slidenotes-"))
    # A private profile avoids clashing with a running LibreOffice instance.
    profile = Path(tempfile.mkdtemp(prefix="slidenotes-lo-")).as_uri()
    cmd = [soffice, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf",
           "--outdir", str(outdir), str(src)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        raise SnError(f"{src.name}: LibreOffice conversion failed ({e})") from e
    pdf = outdir / (src.stem + ".pdf")
    if not pdf.exists():
        raise SnError(f"{src.name}: LibreOffice produced no PDF")
    return pdf


def cached_pdf(src: Path, create: bool = True) -> Path | None:
    """PDF conversion of `src`, cached in .slidenotes/cache/<sha256>.pdf next to it.

    Returns None when LibreOffice is missing (and the cache is empty).
    """
    digest = sha256_file(src)
    cache = work_dir(src) / "cache" / f"{digest}.pdf"
    if cache.exists():
        return cache
    if not create or not find_soffice():
        return None
    pdf = convert_to_pdf(src)
    cache.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(pdf), cache)
    shutil.rmtree(pdf.parent, ignore_errors=True)
    return cache
