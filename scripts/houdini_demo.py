#!/usr/bin/env python3
"""Build a grid and xform inside hython, then capture the SOP.

Run:
    hython scripts/houdini_demo.py --out snapshots/houdini_demo.snapshot.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parityforge.hosts.invocation import HOUDINI_DEMO_EXAMPLE, split_script_args
from parityforge.hosts.runtime import ensure_importable


def build_scene(hou):
    obj = hou.node("/obj")
    if obj is None:
        raise RuntimeError("/obj is missing. Refusing to invent a scene root.")
    geo = obj.createNode("geo", "parityforge_demo")
    for child in list(geo.children()):
        child.destroy()
    grid = geo.createNode("grid", "grid1")
    xform = geo.createNode("xform", "xform1")
    xform.setFirstInput(grid)
    xform.parmTuple("t").set((1.0, 3.0, -2.0))
    xform.setDisplayFlag(True)
    xform.setRenderFlag(True)
    geo.layoutChildren()
    return xform.path()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="scripts/houdini_demo.py",
        description="Create a Houdini grid, move it, and write a ParityForge snapshot.",
        epilog=HOUDINI_DEMO_EXAMPLE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--meters-per-unit", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=None)
    if any(arg in {"-h", "--help"} for arg in argv):
        try:
            parser.parse_args(split_script_args(argv))
        except SystemExit as exc:
            return int(exc.code or 0)
    try:
        import hou
    except ImportError:
        sys.stderr.write(
            "houdini_demo.py must run inside hython, because it imports hou.\n"
            f"Example:\n  {HOUDINI_DEMO_EXAMPLE}\n"
        )
        return 2
    ensure_importable(
        ("numpy", "pydantic"),
        hint=(
            "hython does not see packages installed into another Python.\n"
            "When this hython provides pip:\n"
            "  hython -m pip install 'pydantic>=2.7,<3' numpy\n"
            "v0.1 did not run that command: no licensed hython was available."
        ),
    )
    try:
        args = parser.parse_args(split_script_args(argv))
    except SystemExit as exc:
        return int(exc.code or 0)
    from parityforge.hosts.capture_houdini import capture_hou
    from parityforge.snapshot_io import save_snapshot

    node = build_scene(hou)
    capture_args = argparse.Namespace(out=args.out, hip=None, node=node, seed=args.seed, meters_per_unit=args.meters_per_unit)
    document = capture_hou(hou, capture_args)
    save_snapshot(Path(args.out), document)
    sys.stdout.write(f"Wrote {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
