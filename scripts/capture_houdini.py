#!/usr/bin/env python3
"""hython entry point."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parityforge.hosts.runtime import ensure_importable

ensure_importable(
    ("numpy", "pydantic"),
    hint=(
        "hython does not see packages installed into another Python.\n"
        "When this hython provides pip:\n"
        "  hython -m pip install 'pydantic>=2.7,<3' numpy\n"
        "v0.1 did not run that command: no licensed hython was available."
    ),
)

from parityforge.hosts.capture_houdini import main

if __name__ == "__main__":
    raise SystemExit(main())
