"""Locate the Python interpreter that ships inside a Blender install.

Official Blender builds use that interpreter for ``--python`` scripts. It is
not the ``python`` on ``PATH``, so a normal ``pip install`` does not make
packages visible to capture.
"""

from __future__ import annotations

import os
from pathlib import Path


def _python_bins(root: Path) -> list[Path]:
    found: list[Path] = []
    if not root.is_dir():
        return found
    for child in sorted(root.iterdir()):
        bin_dir = child / "python" / "bin"
        if not bin_dir.is_dir():
            continue
        for path in sorted(bin_dir.iterdir()):
            name = path.name
            if "config" in name or name.endswith((".so", ".dylib", ".dll")):
                continue
            if name == "python.exe" or name.startswith("python3"):
                found.append(path)
    return found


def find_blender_python(blender: Path) -> Path | None:
    """Return Blender's bundled Python, or None when the layout is unrecognized."""
    blender = Path(blender)
    if not blender.is_file():
        return None
    parent = blender.resolve().parent
    roots = [parent]
    if parent.name == "MacOS":
        roots.append(parent.parent / "Resources")
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(_python_bins(root))
    executable = [path for path in candidates if path.is_file() and os.access(path, os.X_OK)]
    if not executable:
        return None

    def rank(path: Path) -> tuple[int, str]:
        name = path.name
        # Prefer an explicit minor version over a generic python3 symlink.
        specific = 1 if name not in {"python3", "python.exe"} else 0
        return (specific, name)

    return sorted(executable, key=rank, reverse=True)[0]
