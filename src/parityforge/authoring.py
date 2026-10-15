"""Write the deterministic fixtures shipped with ParityForge.

The Houdini numbers below are the hand conversion (x, y, z) Blender meters
-> (x, z, -y) Houdini, times 100 when the fixture is stored in centimeters.
They are not produced by asking the comparison engine to convert a snapshot.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np

from .coordinates import NAMED_FORWARD, NAMED_HANDEDNESS, NAMED_TO_CANONICAL, NAMED_UP, shape_parameters
from .snapshot_io import save_snapshot

PLANE = [
    [-1.0, -1.0, 0.0],
    [1.0, -1.0, 0.0],
    [1.0, 1.0, 0.0],
    [-1.0, 1.0, 0.0],
]
FACES = {"face_counts": [4], "face_indices": [0, 1, 2, 3]}
CAPTURED_AT = "2026-10-15T00:00:00Z"


def _basis(name: str) -> dict:
    return {
        "name": name,
        "handedness": NAMED_HANDEDNESS[name],
        "up_axis": NAMED_UP[name],
        "forward_axis": NAMED_FORWARD[name],
        "matrix_to_canonical": NAMED_TO_CANONICAL[name].tolist(),
    }


def _matrix(scale: tuple[float, float, float], translation: tuple[float, float, float]) -> list[list[float]]:
    sx, sy, sz = scale
    tx, ty, tz = translation
    return [
        [sx, 0.0, 0.0, tx],
        [0.0, sy, 0.0, ty],
        [0.0, 0.0, sz, tz],
        [0.0, 0.0, 0.0, 1.0],
    ]


def to_houdini_meters(point: list[float]) -> list[float]:
    x, y, z = point
    return [x, z, -y]


def to_houdini_centimeters(point: list[float]) -> list[float]:
    x, y, z = to_houdini_meters(point)
    return [100.0 * x, 100.0 * y, 100.0 * z]


def _execution(script: str, note: str) -> dict:
    return {
        "captured_at": CAPTURED_AT,
        "host_script": script,
        "command": "python tools/build_fixtures.py",
        "producer": "parityforge.authoring",
        "warnings": [],
        "note": note,
    }


def _identity(
    *,
    snapshot_id: str,
    scene: str,
    asset: str,
    source_app: str,
    seed: int | None,
    meters_per_unit: float,
    length_unit: str,
    angle: str,
) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "scene": scene,
        "asset": asset,
        "source_app": source_app,
        "source_version": "fixture",
        "time": {"frame": 1, "fps": 24, "seconds": 0.0},
        "seed": seed,
        "units": {"length_unit": length_unit, "meters_per_unit": meters_per_unit, "angle": angle},
        "coordinate_basis": _basis(source_app),
    }


def _mesh_object(
    *,
    name: str,
    path: str,
    points: list[list[float]],
    matrix: list[list[float]],
    attributes: list[dict] | None = None,
) -> dict:
    return {
        "name": name,
        "path": path,
        "type": "mesh",
        "transform": {"matrix": matrix},
        "geometry": {
            "space": "local",
            "point_count": len(points),
            "points": points,
            "correspondence": "index",
            **FACES,
        },
        "attributes": attributes or [],
    }


def _write_pair(root: Path, case: str, baseline: dict, candidate: dict, arrays: dict | None = None) -> None:
    case_dir = root / case
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    save_snapshot(case_dir / "blender.snapshot.json", baseline, None if arrays is None else arrays.get("baseline"))
    save_snapshot(case_dir / "houdini.snapshot.json", candidate, None if arrays is None else arrays.get("candidate"))


NOTE = "Authored fixture expressing evaluated output. Not captured from a live DCC process."


def build_transformed(root: Path, *, translation_cm_x: float, case: str, snapshot_suffix: str) -> None:
    blender_matrix = _matrix((2.0, 1.0, 1.0), (1.0, 2.0, 3.0))
    # Hand map of translation (1, 2, 3) m -> (1, 3, -2) m -> centimeters, with an optional X bias.
    houdini_matrix = _matrix((2.0, 1.0, 1.0), (translation_cm_x, 300.0, -200.0))
    houdini_points = [to_houdini_centimeters(point) for point in PLANE]
    blender_parameters = shape_parameters(PLANE, blender_matrix, NAMED_TO_CANONICAL["blender"], 1.0)
    houdini_parameters = shape_parameters(houdini_points, houdini_matrix, NAMED_TO_CANONICAL["houdini"], 0.01)
    if blender_parameters != houdini_parameters:
        raise RuntimeError(f"Plane shape parameters diverged: {blender_parameters} vs {houdini_parameters}")
    baseline = {
        "schema_version": "1.0.0",
        "identity": _identity(
            snapshot_id=f"plane-blender-{snapshot_suffix}",
            scene="PlaneScene",
            asset="Plane",
            source_app="blender",
            seed=None,
            meters_per_unit=1.0,
            length_unit="meter",
            angle="radian",
        ),
        "parameters": blender_parameters,
        "objects": [
            _mesh_object(
                name="Plane",
                path="Plane",
                points=PLANE,
                matrix=blender_matrix,
            )
        ],
        "execution": _execution("scripts/capture_blender.py", NOTE),
    }
    candidate = {
        "schema_version": "1.0.0",
        "identity": _identity(
            snapshot_id=f"plane-houdini-{snapshot_suffix}",
            scene="plane.hip",
            asset="/obj/geo1/OUT",
            source_app="houdini",
            seed=None,
            meters_per_unit=0.01,
            length_unit="centimeter",
            angle="degree",
        ),
        "parameters": houdini_parameters,
        "objects": [
            _mesh_object(
                name="Plane",
                path="/obj/geo1/OUT",
                points=houdini_points,
                matrix=houdini_matrix,
            )
        ],
        "execution": _execution("scripts/capture_houdini.py", NOTE),
    }
    _write_pair(root, case, baseline, candidate)


def build_attribute_case(root: Path) -> None:
    matrix = _matrix((1.0, 1.0, 1.0), (0.0, 0.0, 0.0))
    parameters = {"attribute": "mask"}
    baseline = {
        "schema_version": "1.0.0",
        "identity": _identity(
            snapshot_id="mask-blender",
            scene="MaskScene",
            asset="Plate",
            source_app="blender",
            seed=None,
            meters_per_unit=1.0,
            length_unit="meter",
            angle="radian",
        ),
        "parameters": parameters,
        "objects": [
            _mesh_object(
                name="Plate",
                path="Plate",
                points=PLANE,
                matrix=matrix,
                attributes=[
                    {
                        "name": "mask",
                        "domain": "point",
                        "type": "float",
                        "role": "scalar",
                        "inline": [0.0, 1.0, 0.0, 1.0],
                    }
                ],
            )
        ],
        "execution": _execution("scripts/capture_blender.py", NOTE),
    }
    candidate = {
        "schema_version": "1.0.0",
        "identity": _identity(
            snapshot_id="mask-houdini",
            scene="mask.hip",
            asset="/obj/geo1/OUT",
            source_app="houdini",
            seed=None,
            meters_per_unit=1.0,
            length_unit="meter",
            angle="degree",
        ),
        "parameters": parameters,
        "objects": [
            _mesh_object(
                name="Plate",
                path="/obj/geo1/OUT",
                points=[to_houdini_meters(point) for point in PLANE],
                matrix=matrix,
                attributes=[
                    {
                        "name": "mask",
                        "domain": "face",
                        "type": "float",
                        "role": "scalar",
                        "inline": [0.5],
                    }
                ],
            )
        ],
        "execution": _execution("scripts/capture_houdini.py", NOTE + " mask is a primitive attribute."),
    }
    _write_pair(root, "attribute_domain_mismatch", baseline, candidate)


def _scatter_points(seed: int) -> np.ndarray:
    generator = np.random.Generator(np.random.PCG64(seed))
    xs = generator.uniform(-5.0, 5.0, 5000)
    ys = generator.uniform(-5.0, 5.0, 5000)
    zs = np.zeros(5000)
    return np.column_stack([xs, ys, zs])


def build_scatter(root: Path) -> None:
    baseline_points = _scatter_points(20261015)
    candidate_source = _scatter_points(20261016)
    candidate_points = np.column_stack(
        [
            candidate_source[:, 0],
            candidate_source[:, 2],
            -candidate_source[:, 1],
        ]
    )
    identity_matrix = _matrix((1.0, 1.0, 1.0), (0.0, 0.0, 0.0))
    parameters = {"count": 5000, "seed": 42, "domain": "10m_square"}

    def document(snapshot_id: str, scene: str, source_app: str, npz_name: str) -> dict:
        return {
            "schema_version": "1.0.0",
            "identity": _identity(
                snapshot_id=snapshot_id,
                scene=scene,
                asset="Scatter",
                source_app=source_app,
                seed=42,
                meters_per_unit=1.0,
                length_unit="meter",
                angle="radian" if source_app == "blender" else "degree",
            ),
            "parameters": parameters,
            "objects": [
                {
                    "name": "Scatter",
                    "path": "Scatter" if source_app == "blender" else "/obj/geo1/OUT",
                    "type": "instances",
                    "transform": {"matrix": identity_matrix},
                    "instances": {
                        "count": 5000,
                        "prototype": "Rock",
                        "space": "world",
                        "positions_npz": npz_name,
                        "positions_key": "positions",
                        "correspondence": "none",
                    },
                    "attributes": [],
                }
            ],
            "execution": _execution(
                "scripts/capture_blender.py" if source_app == "blender" else "scripts/capture_houdini.py",
                NOTE + " Positions come from independent uniform streams. The declared seed matches; the samples do not.",
            ),
        }

    case_dir = root / "seeded_scatter"
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    save_snapshot(
        case_dir / "blender.snapshot.json",
        document("scatter-blender", "ScatterScene", "blender", "blender_instances.npz"),
        {"blender_instances.npz": {"positions": baseline_points}},
    )
    save_snapshot(
        case_dir / "houdini.snapshot.json",
        document("scatter-houdini", "scatter.hip", "houdini", "houdini_instances.npz"),
        {"houdini_instances.npz": {"positions": candidate_points}},
    )


def write_configs(root: Path) -> None:
    identity = 'schema_version = "1.0.0"\nintent = "identity"\n'
    scatter = """schema_version = "1.0.0"
intent = "distribution"

# 5,000 uniform samples on a 10 m square. These are distribution tolerances,
# not vertex tolerances. A 0.4 m centroid bias still fails the 0.25 m gate.
[tolerances.centroid]
absolute = 0.25
relative = 0.0
unit = "meter"
minimum_samples = 1

[tolerances.bounds]
absolute = 0.5
relative = 0.0
unit = "meter"
minimum_samples = 1
"""
    for case in ("transformed_primitive", "incorrect_transform", "attribute_domain_mismatch"):
        (root / case / "parityforge.toml").write_text(identity, encoding="utf-8")
    (root / "seeded_scatter" / "parityforge.toml").write_text(scatter, encoding="utf-8")
    (root / "parityforge.toml").write_text(identity, encoding="utf-8")


def write_suite(root: Path) -> None:
    text = """schema_version: "1.0.0"
cases:
  - id: transformed_primitive
    description: True positive with Houdini Y-up and centimeter units.
    baseline: transformed_primitive/blender.snapshot.json
    candidate: transformed_primitive/houdini.snapshot.json
    config: transformed_primitive/parityforge.toml
    expect:
      overall: PASS
      equality_claim: exact_match
      labels: [exact_match]
  - id: incorrect_transform
    description: Same primitive with an extra 0.4 m of Houdini X translation.
    baseline: incorrect_transform/blender.snapshot.json
    candidate: incorrect_transform/houdini.snapshot.json
    config: incorrect_transform/parityforge.toml
    expect:
      overall: FAIL
      equality_claim: not_equal
      metrics:
        centroid: FAIL
        point_count: PASS
        surface_area: PASS
  - id: seeded_scatter
    description: Same count and seed, independent uniform samples.
    baseline: seeded_scatter/blender.snapshot.json
    candidate: seeded_scatter/houdini.snapshot.json
    config: seeded_scatter/parityforge.toml
    nodebridge_link: nodebridge_scatter/link.json
    expect:
      overall: PASS
      equality_claim: statistical_similarity
      labels: [equivalent_in_distribution, statistical_similarity]
      metrics:
        instance_count: PASS
        vertex_position: NOT_EVALUATED
        seed: PASS
  - id: attribute_domain_mismatch
    description: Same quad, mask stored on points versus faces.
    baseline: attribute_domain_mismatch/blender.snapshot.json
    candidate: attribute_domain_mismatch/houdini.snapshot.json
    config: attribute_domain_mismatch/parityforge.toml
    expect:
      overall: FAIL
      equality_claim: not_equal
      metrics:
        attribute_schema: FAIL
        attribute_values: NOT_EVALUATED
        point_count: PASS
"""
    (root / "suite.yaml").write_text(text, encoding="utf-8")


def write_nodebridge_link(root: Path, report_text: str) -> None:
    import json

    case = root / "nodebridge_scatter"
    case.mkdir(parents=True, exist_ok=True)
    (case / "expected_report_houdini.txt").write_text(report_text, encoding="utf-8")
    note = (
        "The report text is the NodeBridge scatter Houdini report at the audited commit. "
        "The evaluated snapshots are authored ParityForge fixtures for an EQUIVALENT scatter, "
        "not a live cook of generated_houdini.py."
    )
    link = {
        "repository": "https://github.com/Plygonality/NodeBridge",
        "audited_commit": "21d5ca9cc43f09ac173a5e487003f6bc13ac33bf",
        "source_graph": "examples/scatter/scatter.graph.json",
        "translation_report": "expected_report_houdini.txt",
        "operation_kind": "SCATTER",
        "note": note,
    }
    (case / "link.json").write_text(json.dumps(link, indent=2) + "\n", encoding="utf-8")


def build_all(root: Path, nodebridge_report: str) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    build_transformed(root, translation_cm_x=100.0, case="transformed_primitive", snapshot_suffix="match")
    build_transformed(root, translation_cm_x=140.0, case="incorrect_transform", snapshot_suffix="bias")
    build_attribute_case(root)
    build_scatter(root)
    write_configs(root)
    write_nodebridge_link(root, nodebridge_report)
    write_suite(root)
