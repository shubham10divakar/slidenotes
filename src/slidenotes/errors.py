"""Error types. Every error names the file, the problem and the command that fixes it."""

from __future__ import annotations

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_USAGE = 2
EXIT_LOCKED = 3


class SnError(Exception):
    """Base error; `exit_code` follows the documented exit codes."""

    exit_code = EXIT_USAGE

    def __init__(self, message: str, fix: str | None = None):
        super().__init__(message)
        self.message = message
        self.fix = fix

    def __str__(self) -> str:
        if self.fix:
            return f"{self.message} → run {self.fix}"
        return self.message


class UsageError(SnError):
    exit_code = EXIT_USAGE


class ValidationError(SnError):
    exit_code = EXIT_VALIDATION


class LockedError(SnError):
    """File locked (open in Word) or unreadable."""

    exit_code = EXIT_LOCKED


class ToolMissing(SnError):
    """An optional external tool (LibreOffice, pandoc) is not installed."""

    exit_code = EXIT_USAGE


class AmbiguousTarget(SnError):
    """Several sections match TARGET; carries the candidates so the CLI can ask."""

    exit_code = EXIT_USAGE

    def __init__(self, message: str, candidates: list):
        super().__init__(message, fix=None)
        self.candidates = candidates
