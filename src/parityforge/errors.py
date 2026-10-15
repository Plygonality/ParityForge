"""Actionable errors. Messages name the failure and the next step."""

from __future__ import annotations


class ParityError(Exception):
    """Base error. ``hint`` is appended so CLIs can print one block."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        self.hint = hint
        text = message if not hint else f"{message}\nHint: {hint}"
        super().__init__(text)


class SchemaError(ParityError):
    """A snapshot or config failed validation."""


class HostError(ParityError):
    """A DCC capture could not run."""
