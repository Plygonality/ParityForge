#!/usr/bin/env python3
"""Build a transformed plane inside Blender and capture it.

Run:
    blender --background --factory-startup --python scripts/blender_demo.py -- --out snapshots/blender_demo.snapshot.json
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parityforge.hosts.invocation import BLENDER_DEMO_EXAMPLE
from parityforge.hosts.runtime import ensure_importable


def build_scene(bpy) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(1.0, 2.0, 3.0))
    obj = bpy.context.active_object
    obj.name = "Plane"
    obj.scale = (2.0, 1.0, 1.0)
    bpy.context.view_layer.update()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    try:
        import bpy
    except ImportError:
        sys.stderr.write(
            "blender_demo.py must run inside Blender.\n"
            f"Example:\n  {BLENDER_DEMO_EXAMPLE}\n"
        )
        return 2
    ensure_importable(
        ("numpy", "pydantic"),
        hint=(
            "Blender's Python is separate from the interpreter that installed ParityForge.\n"
            "Official builds include numpy and omit pydantic. From the repository root:\n"
            "  python tools/install_blender_host_deps.py --blender /path/to/blender"
        ),
    )
    from parityforge.hosts.capture_blender import capture_bpy, parse_args
    from parityforge.snapshot_io import save_snapshot

    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    build_scene(bpy)
    document = capture_bpy(bpy, args)
    save_snapshot(Path(args.out), document)
    sys.stdout.write(f"Wrote {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
