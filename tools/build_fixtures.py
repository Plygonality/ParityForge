#!/usr/bin/env python3
"""Regenerate fixtures/ from the authoring module."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parityforge.authoring import build_all


def main() -> int:
    report = Path("/tmp/audit/scatter_report_houdini.txt")
    if not report.is_file():
        fallback = ROOT / "fixtures" / "nodebridge_scatter" / "expected_report_houdini.txt"
        report = fallback
    if not report.is_file():
        print("NodeBridge scatter report text is missing.", file=sys.stderr)
        return 1
    build_all(ROOT / "fixtures", report.read_text(encoding="utf-8"))
    print(f"Wrote fixtures under {ROOT / 'fixtures'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
