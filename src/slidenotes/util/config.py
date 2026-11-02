from __future__ import annotations

import os
from pathlib import Path

ENV_HOME = "SLIDENOTES_HOME"


def home() -> Path:
    """Folder holding library.md: $SLIDENOTES_HOME, else ~/.slidenotes."""
    value = os.environ.get(ENV_HOME)
    if value:
        return Path(value).expanduser()
    return Path.home() / ".slidenotes"


def library_path() -> Path:
    return home() / "library.md"


def work_dir(next_to: Path) -> Path:
    """The `.slidenotes/` folder that sits next to a source or notes file."""
    return next_to.parent / ".slidenotes"
