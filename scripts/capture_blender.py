#!/usr/bin/env python3
"""Blender entry point. Blender runs this file with --python."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parityforge.hosts.runtime import ensure_importable

ensure_importable(
    ("numpy", "pydantic"),
    hint=(
        "Blender's Python is separate from the interpreter that installed ParityForge.\n"
        "Official builds include numpy and omit pydantic. From the repository root:\n"
        "  python tools/install_blender_host_deps.py --blender /path/to/blender"
    ),
)

from parityforge.hosts.capture_blender import main

if __name__ == "__main__":
    raise SystemExit(main())
