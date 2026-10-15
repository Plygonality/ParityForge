"""Capture an evaluated Houdini SOP. This module imports hou only in ``main``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from parityforge.coordinates import NAMED_FORWARD, NAMED_HANDEDNESS, NAMED_TO_CANONICAL, NAMED_UP
from parityforge.errors import HostError
from parityforge.hosts.invocation import HOUDINI_CAPTURE_EXAMPLE, MIN_HOUDINI, split_script_args
from parityforge.snapshot_io import save_snapshot

MISSING = (
    "capture_houdini.py must run inside Houdini's hython, because it imports hou.\n"
    f"Example:\n  {HOUDINI_CAPTURE_EXAMPLE}\n"
)


def parser() -> argparse.ArgumentParser:
    tool = argparse.ArgumentParser(
        prog="scripts/capture_houdini.py",
        description="Export an evaluated Houdini SOP to a ParityForge snapshot.",
        epilog=HOUDINI_CAPTURE_EXAMPLE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tool.add_argument("--out", required=True, help="Destination .snapshot.json path")
    tool.add_argument("--hip", default=None, help="Optional .hip file to load before cooking")
    tool.add_argument("--node", required=True, help="SOP node path, for example /obj/geo1/OUT")
    tool.add_argument("--seed", type=int, default=None, help="Declared procedural seed to record")
    tool.add_argument(
        "--meters-per-unit",
        type=float,
        default=1.0,
        help="Declared length of one Houdini unit in meters. Default 1. Not inferred from the hip.",
    )
    return tool


def parse_args(argv: list[str]) -> argparse.Namespace:
    return parser().parse_args(split_script_args(argv))


def _version_tuple(hou: Any) -> tuple[int, int]:
    raw = tuple(hou.applicationVersion())
    return int(raw[0]), int(raw[1])


def _matrix_from_hou(matrix: Any) -> list[list[float]]:
    values = list(matrix.asTuple())
    if len(values) != 16:
        raise HostError(f"Expected 16 matrix values, got {len(values)}.")
    return [values[row * 4 : (row + 1) * 4] for row in range(4)]


def _identity() -> list[list[float]]:
    return [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def _world_matrix(hou: Any, node: Any, warnings: list[str]) -> list[list[float]]:
    current = node
    while current is not None:
        type_name = ""
        try:
            type_name = current.type().name()
        except Exception:
            type_name = ""
        if type_name == "geo" and hasattr(current, "worldTransform"):
            try:
                return _matrix_from_hou(current.worldTransform())
            except Exception as exc:
                warnings.append(f"Could not read worldTransform on {current.path()}: {exc}")
                return _identity()
        current = current.parent()
    warnings.append("No parent geo node with worldTransform. Recorded an identity transform.")
    return _identity()


def _attrib_values(hou: Any, geo: Any, attrib: Any, domain: str, warnings: list[str]) -> dict[str, Any] | None:
    name = attrib.name()
    if name == "P":
        return None
    data_type = attrib.dataType()
    size = int(attrib.size())
    float_type = getattr(getattr(hou, "attribData", None), "Float", None)
    int_type = getattr(getattr(hou, "attribData", None), "Int", None)
    try:
        if domain == "point":
            floats = geo.pointFloatAttribValues
            ints = geo.pointIntAttribValues
        else:
            floats = geo.primFloatAttribValues
            ints = geo.primIntAttribValues
        if data_type == float_type and size == 1:
            values = [float(value) for value in floats(name)]
            return {
                "name": name,
                "domain": "point" if domain == "point" else "face",
                "type": "float",
                "role": "scalar",
                "inline": values,
            }
        if data_type == float_type and size == 3:
            raw = [float(value) for value in floats(name)]
            values = [raw[index : index + 3] for index in range(0, len(raw), 3)]
            return {
                "name": name,
                "domain": "point" if domain == "point" else "face",
                "type": "vector3",
                "role": "unknown",
                "inline": values,
            }
        if data_type == int_type and size == 1:
            values = [int(value) for value in ints(name)]
            return {"name": name, "domain": "point" if domain == "point" else "face", "type": "int", "role": "scalar", "inline": values}
    except Exception as exc:
        warnings.append(f"Attribute {name!r} could not be read: {exc}")
        return None
    warnings.append(
        f"Attribute {name!r} type {data_type!r} size {size} is unsupported and was not given a passing value."
    )
    return None


def capture_hou(hou: Any, args: argparse.Namespace) -> dict[str, Any]:
    major, minor = _version_tuple(hou)
    if (major, minor) < MIN_HOUDINI:
        raise HostError(
            f"Houdini {major}.{minor} is older than {MIN_HOUDINI[0]}.{MIN_HOUDINI[1]}.",
            hint="Use Houdini 19.5 or newer.",
        )
    if args.meters_per_unit <= 0:
        raise HostError(
            f"--meters-per-unit must be positive, got {args.meters_per_unit}.",
            hint="Use 1 for meters or 0.01 if this hip stores centimeters.",
        )
    if args.hip:
        hou.hipFile.load(args.hip, suppress_save_prompt=True)
    node = hou.node(args.node)
    if node is None:
        raise HostError(
            f"Node {args.node!r} does not exist.",
            hint="Pass a SOP path such as /obj/geo1/OUT.",
        )
    geometry = node.geometry()
    if geometry is None:
        raise HostError(
            f"{args.node} has no SOP geometry.",
            hint="Cook a SOP and pass that node. OBJ containers themselves are not captured.",
        )
    warnings: list[str] = []
    points = []
    for point in geometry.points():
        position = point.position()
        points.append([float(position[0]), float(position[1]), float(position[2])])
    counts: list[int] = []
    indices: list[int] = []
    instance_positions = []
    polygon = hou.primType.Polygon
    packed = getattr(hou.primType, "PackedPrim", None)
    for prim in geometry.prims():
        prim_type = prim.type()
        if prim_type == polygon:
            vertices = [int(vertex.point().number()) for vertex in prim.vertices()]
            if len(vertices) < 3:
                warnings.append(f"Skipped a polygon with {len(vertices)} vertices.")
                continue
            counts.append(len(vertices))
            indices.extend(vertices)
        elif packed is not None and prim_type == packed:
            translates = prim.fullTransform().extractTranslates()
            instance_positions.append([float(translates[0]), float(translates[1]), float(translates[2])])
    attributes = []
    for attrib in geometry.pointAttribs():
        payload = _attrib_values(hou, geometry, attrib, "point", warnings)
        if payload:
            attributes.append(payload)
    for attrib in geometry.primAttribs():
        payload = _attrib_values(hou, geometry, attrib, "prim", warnings)
        if payload:
            attributes.append(payload)
    obj: dict[str, Any] = {
        "name": node.name(),
        "path": node.path(),
        "type": "mesh" if counts else "points",
        "transform": {"matrix": _world_matrix(hou, node, warnings)},
        "attributes": attributes,
    }
    if points:
        geometry_payload: dict[str, Any] = {
            "space": "local",
            "point_count": len(points),
            "points": points,
            "correspondence": "none",
        }
        if counts:
            geometry_payload["face_counts"] = counts
            geometry_payload["face_indices"] = indices
        obj["geometry"] = geometry_payload
    if instance_positions:
        obj["type"] = "instances" if not counts else obj["type"]
        obj["instances"] = {
            "count": len(instance_positions),
            "space": "local",
            "positions": instance_positions,
            "correspondence": "none",
            "prototype": None,
        }
    if "geometry" not in obj and "instances" not in obj:
        raise HostError(
            f"{args.node} cooked, but it has no points.",
            hint="Check that the display SOP produces points or packed primitives.",
        )
    frame = float(hou.frame())
    fps = float(hou.fps())
    basis = NAMED_TO_CANONICAL["houdini"].tolist()
    return {
        "schema_version": "1.0.0",
        "identity": {
            "snapshot_id": f"houdini-{node.name()}",
            "scene": Path(args.hip).stem if args.hip else "hip",
            "asset": node.path(),
            "source_app": "houdini",
            "source_version": str(hou.applicationVersionString()),
            "time": {"frame": frame, "fps": fps, "seconds": 0.0 if fps == 0 else (frame - 1.0) / fps},
            "seed": args.seed,
            "units": {
                "length_unit": "houdini",
                "meters_per_unit": float(args.meters_per_unit),
                "angle": "degree",
            },
            "coordinate_basis": {
                "name": "houdini",
                "handedness": NAMED_HANDEDNESS["houdini"],
                "up_axis": NAMED_UP["houdini"],
                "forward_axis": NAMED_FORWARD["houdini"],
                "matrix_to_canonical": basis,
            },
        },
        "parameters": {},
        "objects": [obj],
        "execution": {
            "captured_at": "live",
            "host_script": "scripts/capture_houdini.py",
            "command": HOUDINI_CAPTURE_EXAMPLE,
            "producer": "parityforge.hosts.capture_houdini",
            "warnings": warnings,
            "note": (
                "SOP points are in geo-local space. The parent geo worldTransform is the object matrix. "
                "Units come from --meters-per-unit."
            ),
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
        import hou
    except ImportError:
        sys.stderr.write(MISSING)
        return 2
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        document = capture_hou(hou, args)
        save_snapshot(Path(args.out), document)
    except HostError as exc:
        sys.stderr.write(f"{exc}\n")
        return 3
    except Exception as exc:
        sys.stderr.write(f"Houdini capture failed: {exc}\nHint: {HOUDINI_CAPTURE_EXAMPLE}\n")
        return 1
    sys.stdout.write(f"Wrote {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
