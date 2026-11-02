"""Open files in system apps; jump to a PDF page where a known viewer supports it."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from slidenotes.errors import SnError
from slidenotes.util.paths import display

_WIN_VIEWERS = [
    (r"%LOCALAPPDATA%\SumatraPDF\SumatraPDF.exe", ["-page", "{page}", "{file}"]),
    (r"%ProgramFiles%\SumatraPDF\SumatraPDF.exe", ["-page", "{page}", "{file}"]),
    (r"%ProgramFiles%\Adobe\Acrobat DC\Acrobat\Acrobat.exe", ["/A", "page={page}", "{file}"]),
    (r"%ProgramFiles(x86)%\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe", ["/A", "page={page}", "{file}"]),
]
_UNIX_VIEWERS = [
    ("zathura", ["--page={page}", "{file}"]),
    ("evince", ["--page-index={page}", "{file}"]),
    ("okular", ["-p", "{page}", "{file}"]),
    ("SumatraPDF", ["-page", "{page}", "{file}"]),
]


def _spawn(cmd: list[str]) -> None:
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=(sys.platform != "win32"))


def open_default(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            _spawn(["open", str(path)])
        else:
            _spawn(["xdg-open", str(path)])
    except OSError as e:
        raise SnError(f"{display(path)}: cannot open ({e})") from e


def open_pdf_at(path: Path, page: int | None) -> bool:
    """Open a PDF, at `page` when a supported viewer is found. Returns True if the page was honoured."""
    if page:
        if sys.platform == "win32":
            for exe, args in _WIN_VIEWERS:
                exe = os.path.expandvars(exe)
                if Path(exe).exists():
                    _spawn([exe] + [a.format(page=page, file=path) for a in args])
                    return True
        elif sys.platform == "darwin":
            # Preview can't be told a page; Skim can via AppleScript-free CLI only when installed.
            pass
        else:
            for exe, args in _UNIX_VIEWERS:
                found = shutil.which(exe)
                if found:
                    _spawn([found] + [a.format(page=page, file=path) for a in args])
                    return True
    open_default(path)
    return False
