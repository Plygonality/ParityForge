#!/usr/bin/env python3
"""Print DCC lane status for CI. Missing hython is NOT_RUN, not a failure."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parityforge.doctor import diagnose


def main() -> int:
    report = diagnose()
    houdini = report["houdini"]["lane"]
    blender = "available" if report["blender"]["status"] == "available" else "NOT_RUN"
    payload = {
        "blender": blender,
        "houdini": houdini,
        "unreal": report["unreal"]["lane"],
        "offline": report["offline"]["status"],
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if payload["offline"] != "available":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
