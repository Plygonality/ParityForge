#!/usr/bin/env python3
"""Install the packages Blender's own Python needs in order to capture.

Official Blender builds ship numpy. They do not ship pydantic. Capture imports
pydantic so an invalid snapshot is refused before it is written. Installing
into the system interpreter does not affect ``blender --python``.

    python tools/install_blender_host_deps.py --blender /path/to/blender
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parityforge.hosts.blender_python import find_blender_python

PIN = "pydantic>=2.7,<3"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", required=True, help="Path to the blender executable")
    args = parser.parse_args(argv)
    blender = Path(args.blender)
    python = find_blender_python(blender)
    if python is None:
        sys.stderr.write(
            f"Could not find a Python binary beside {blender}.\n"
            "Expected <blender-dir>/<version>/python/bin/python3.* "
            "(or Contents/Resources on macOS).\n"
            "Install pydantic into that interpreter yourself, then rerun the capture.\n"
        )
        return 1
    print(f"Blender Python: {python}")
    subprocess.run([str(python), "-m", "ensurepip", "--upgrade"], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", PIN], check=True)
    probe = subprocess.run(
        [str(python), "-c", "import pydantic, numpy; print(pydantic.__version__, numpy.__version__)"],
        check=True,
        capture_output=True,
        text=True,
    )
    print(f"Installed into Blender: pydantic {probe.stdout.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
