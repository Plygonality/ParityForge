"""Import checks for scripts that run inside a DCC interpreter."""

from __future__ import annotations

import sys


def missing_modules(names: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for name in names:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    return missing


def ensure_importable(names: tuple[str, ...], *, hint: str) -> None:
    missing = missing_modules(names)
    if not missing:
        return
    sys.stderr.write(
        "This host interpreter cannot import: "
        + ", ".join(missing)
        + ".\n"
        + hint
        + "\n"
    )
    raise SystemExit(1)
