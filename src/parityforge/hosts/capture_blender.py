"""Capture an evaluated Blender scene. This module imports bpy only in ``main``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from parityforge.coordinates import NAMED_FORWARD, NAMED_HANDEDNESS, NAMED_TO_CANONICAL, NAMED_UP
from parityforge.errors import HostError
from parityforge.hosts.invocation import BLENDER_CAPTURE_EXAMPLE, MIN_BLENDER, split_script_args
from parityforge.snapshot_io import save_snapshot

MISSING = (
    "capture_blender.py must run inside Blender, because it imports bpy.\n"
    f"Example:\n  {BLENDER_CAPTURE_EXAMPLE}\n"
)

DOMAIN_MAP = {"POINT": "point", "EDGE": "edge", "FACE": "face", "CORNER": "corner"}


def parser() -> argparse.ArgumentParser:
    tool = argparse.ArgumentParser(
        prog="scripts/capture_blender.py",
        description="Export evaluated Blender geometry to a ParityForge snapshot.",
        epilog=BLENDER_CAPTURE_EXAMPLE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tool.add_argument("--out", required=True, help="Destination .snapshot.json path")
    tool.add_argument("--seed", type=int, default=None, help="Declared procedural seed to record")
    tool.add_argument("--object", action="append", dest="objects", help="Object name to export. Repeatable.")
    tool.add_argument("--scene", default=None, help="Scene name override")
    return tool


def parse_args(argv: list[str]) -> argparse.Namespace:
    return parser().parse_args(split_script_args(argv))


def _matrix(matrix: Any) -> list[list[float]]:
    return [[float(value) for value in row] for row in matrix]


def _read_attributes(mesh: Any, warnings: list[str]) -> list[dict[str, Any]]:
    attributes = []
    collection = getattr(mesh, "attributes", None)
    if collection is None:
        warnings.append("Mesh has no attributes collection; no attributes were exported.")
        return attributes
    for attr in collection:
        domain = DOMAIN_MAP.get(getattr(attr, "domain", ""), "")
        if not domain:
            warnings.append(f"Attribute {attr.name!r} domain {getattr(attr, 'domain', None)!r} was not exported.")
            continue
        data_type = getattr(attr, "data_type", "")
        try:
            if data_type == "FLOAT":
                values = [float(item.value) for item in attr.data]
                kind = "float"
                role = "scalar"
            elif data_type == "INT":
                values = [int(item.value) for item in attr.data]
                kind = "int"
                role = "scalar"
            elif data_type == "BOOLEAN":
                values = [1 if item.value else 0 for item in attr.data]
                kind = "int"
                role = "scalar"
            elif data_type == "FLOAT_VECTOR":
                values = [[float(component) for component in item.vector] for item in attr.data]
                kind = "vector3"
                role = "unknown"
            else:
                warnings.append(
                    f"Attribute {attr.name!r} type {data_type!r} is unsupported and was not given a passing value."
                )
                continue
        except Exception as exc:
            warnings.append(f"Attribute {attr.name!r} could not be read: {exc}")
            continue
        attributes.append(
            {
                "name": attr.name,
                "domain": domain,
                "type": kind,
                "role": role,
                "inline": values,
            }
        )
    return attributes


def _capture_mesh(obj: Any, depsgraph: Any, warnings: list[str]) -> dict[str, Any] | None:
    evaluated = obj.evaluated_get(depsgraph)
    try:
        mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    except TypeError:
        mesh = evaluated.to_mesh()
    if mesh is None:
        warnings.append(f"{obj.name}: evaluated mesh is None.")
        return None
    try:
        points = [[float(vertex.co.x), float(vertex.co.y), float(vertex.co.z)] for vertex in mesh.vertices]
        counts: list[int] = []
        indices: list[int] = []
        for polygon in mesh.polygons:
            verts = [int(index) for index in polygon.vertices]
            if len(verts) < 3:
                warnings.append(f"{obj.name}: skipped a polygon with {len(verts)} vertices.")
                continue
            counts.append(len(verts))
            indices.extend(verts)
        geometry: dict[str, Any] = {
            "space": "local",
            "point_count": len(points),
            "points": points,
            "correspondence": "none",
        }
        if counts:
            geometry["face_counts"] = counts
            geometry["face_indices"] = indices
        return {
            "name": obj.name,
            "path": obj.name,
            "type": "mesh",
            "transform": {"matrix": _matrix(evaluated.matrix_world)},
            "geometry": geometry,
            "attributes": _read_attributes(mesh, warnings),
        }
    finally:
        evaluated.to_mesh_clear()


def _capture_instances(depsgraph: Any, warnings: list[str], names: set[str] | None) -> dict[str, Any] | None:
    positions = []
    ids = []
    saw_nonzero = False
    for instance in depsgraph.object_instances:
        if not getattr(instance, "is_instance", False):
            continue
        parent = getattr(instance, "parent", None)
        parent_name = getattr(parent, "name", "")
        if names is not None and parent_name not in names and getattr(instance.instance_object, "name", "") not in names:
            continue
        matrix = instance.matrix_world
        translation = matrix.translation
        positions.append([float(translation.x), float(translation.y), float(translation.z)])
        persistent = tuple(getattr(instance, "persistent_id", ()) or ())
        value = int(persistent[0]) if persistent else 0
        if value != 0:
            saw_nonzero = True
        ids.append(value)
    if not positions:
        return None
    payload: dict[str, Any] = {
        "count": len(positions),
        "space": "world",
        "positions": positions,
        "correspondence": "none",
        "prototype": None,
    }
    if saw_nonzero:
        payload["ids"] = ids
    else:
        warnings.append("Instance persistent ids were all zero. Ids were not invented.")
    return payload


def capture_bpy(bpy: Any, args: argparse.Namespace) -> dict[str, Any]:
    version = tuple(int(part) for part in bpy.app.version[:3])
    if version < MIN_BLENDER:
        raise HostError(
            f"Blender {version} is older than {MIN_BLENDER}.",
            hint="Use Blender 3.6 or newer so the evaluated depsgraph and mesh.attributes are available.",
        )
    scene = bpy.context.scene
    if hasattr(bpy.context, "view_layer"):
        bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    warnings: list[str] = []
    selected = set(args.objects) if args.objects else None
    objects = []
    for obj in scene.objects:
        if selected is not None and obj.name not in selected:
            continue
        if obj.type != "MESH":
            continue
        captured = _capture_mesh(obj, depsgraph, warnings)
        if captured is not None:
            objects.append(captured)
    instances = _capture_instances(depsgraph, warnings, selected)
    if instances is not None:
        objects.append(
            {
                "name": "Instances",
                "path": "depsgraph.object_instances",
                "type": "instances",
                "transform": {"matrix": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]},
                "instances": instances,
                "attributes": [],
            }
        )
    if not objects:
        raise HostError(
            "No mesh objects or instances were exported.",
            hint="The scene needs a mesh, or pass --object Name. Camera and light objects are skipped.",
        )
    scale = float(scene.unit_settings.scale_length)
    frame = float(scene.frame_current)
    fps = float(scene.render.fps)
    basis = NAMED_TO_CANONICAL["blender"].tolist()
    return {
        "schema_version": "1.0.0",
        "identity": {
            "snapshot_id": f"blender-{scene.name}",
            "scene": args.scene or scene.name,
            "asset": objects[0]["name"],
            "source_app": "blender",
            "source_version": str(bpy.app.version_string),
            "time": {"frame": frame, "fps": fps, "seconds": 0.0 if fps == 0 else (frame - 1.0) / fps},
            "seed": args.seed,
            "units": {"length_unit": "blender", "meters_per_unit": scale, "angle": "radian"},
            "coordinate_basis": {
                "name": "blender",
                "handedness": NAMED_HANDEDNESS["blender"],
                "up_axis": NAMED_UP["blender"],
                "forward_axis": NAMED_FORWARD["blender"],
                "matrix_to_canonical": basis,
            },
        },
        "parameters": {},
        "objects": objects,
        "execution": {
            "captured_at": "live",
            "host_script": "scripts/capture_blender.py",
            "command": BLENDER_CAPTURE_EXAMPLE,
            "producer": "parityforge.hosts.capture_blender",
            "warnings": warnings,
            "note": "Points come from the evaluated depsgraph mesh in object-local space. The world matrix is matrix_world.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if any(arg in {"-h", "--help"} for arg in argv):
        try:
            parse_args(argv)
        except SystemExit as exc:
            return int(exc.code or 0)
    try:
        import bpy
    except ImportError:
        sys.stderr.write(MISSING)
        return 2
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        document = capture_bpy(bpy, args)
        save_snapshot(Path(args.out), document)
    except HostError as exc:
        sys.stderr.write(f"{exc}\n")
        return 3
    except Exception as exc:
        sys.stderr.write(
            "Blender capture failed: "
            f"{exc}\nHint: run from the repository root so the snapshot writer can import parityforge.\n"
        )
        return 1
    sys.stdout.write(f"Wrote {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
