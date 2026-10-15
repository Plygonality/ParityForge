"""Command lines the capture scripts actually implement.

Doctor, the README test, and the host scripts share these strings so the
documentation cannot drift from argparse.
"""

from __future__ import annotations

BLENDER_CAPTURE_EXAMPLE = (
    "blender --background scene.blend --python scripts/capture_blender.py -- "
    "--out snapshots/scene.snapshot.json"
)
HOUDINI_CAPTURE_EXAMPLE = (
    "hython scripts/capture_houdini.py --hip scene.hip --node /obj/geo1/OUT "
    "--out snapshots/scene.snapshot.json"
)
BLENDER_DEMO_EXAMPLE = (
    "blender --background --factory-startup --python scripts/blender_demo.py -- "
    "--out snapshots/blender_demo.snapshot.json"
)
HOUDINI_DEMO_EXAMPLE = (
    "hython scripts/houdini_demo.py --out snapshots/houdini_demo.snapshot.json"
)

MIN_BLENDER = (3, 6, 0)
MIN_HOUDINI = (19, 5)


def split_script_args(argv: list[str]) -> list[str]:
    """Arguments after ``--``, which is how Blender forwards script args.

    hython leaves a normal ``sys.argv``. If ``--`` is present it still wins,
    so one parser handles both hosts.
    """
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    if argv and argv[0].endswith(".py"):
        return argv[1:]
    return argv[1:]
