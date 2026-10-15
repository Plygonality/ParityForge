from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from parityforge.cli import main
from parityforge.doctor import diagnose
from parityforge.errors import HostError
from parityforge.hosts.capture_blender import capture_bpy
from parityforge.hosts.capture_blender import main as blender_main
from parityforge.hosts.capture_houdini import capture_hou
from parityforge.hosts.capture_houdini import main as houdini_main
from parityforge.hosts.invocation import BLENDER_CAPTURE_EXAMPLE, HOUDINI_CAPTURE_EXAMPLE
from parityforge.hosts.unreal import capture_unreal
from parityforge.nodebridge_link import load_link, parse_translation_report
from parityforge.snapshot_io import load_snapshot


def test_cli_suite_and_validate(tmp_path: Path, capsys) -> None:
    assert main(["validate", "fixtures/transformed_primitive/blender.snapshot.json"]) == 0
    out = tmp_path / "suite"
    assert main(["suite", "fixtures/suite.yaml", "--out", str(out)]) == 0
    suite = json.loads((out / "suite.json").read_text(encoding="utf-8"))
    assert suite["passed"] is True
    assert (out / "index.html").is_file()
    assert (out / "incorrect_transform" / "report.html").is_file()
    html = (out / "incorrect_transform" / "report.html").read_text(encoding="utf-8")
    assert "FAIL" in html
    assert "0.4" in html
    scatter = (out / "seeded_scatter" / "report.json").read_text(encoding="utf-8")
    assert "nodebridge" in scatter
    assert "EQUIVALENT" in scatter


def test_compare_exit_codes(tmp_path: Path) -> None:
    out_pass = tmp_path / "pass"
    out_fail = tmp_path / "fail"
    assert (
        main(
            [
                "compare",
                "fixtures/transformed_primitive/blender.snapshot.json",
                "fixtures/transformed_primitive/houdini.snapshot.json",
                "--config",
                "fixtures/transformed_primitive/parityforge.toml",
                "--out",
                str(out_pass),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "compare",
                "fixtures/incorrect_transform/blender.snapshot.json",
                "fixtures/incorrect_transform/houdini.snapshot.json",
                "--config",
                "fixtures/incorrect_transform/parityforge.toml",
                "--out",
                str(out_fail),
            ]
        )
        == 1
    )


def test_doctor_does_not_invent_missing_software(capsys) -> None:
    report = diagnose()
    assert report["offline"]["status"] == "available"
    assert report["unreal"]["status"] == "deferred"
    assert report["unreal"]["lane"] == "NOT_RUN"
    assert main(["doctor"]) == 0
    text = capsys.readouterr().out
    assert BLENDER_CAPTURE_EXAMPLE in text
    assert HOUDINI_CAPTURE_EXAMPLE in text
    assert "not found" in text or report["blender"]["status"] in {"unavailable", "available", "found_but_unusable"}


def test_capture_scripts_fail_closed_outside_the_dcc(capsys) -> None:
    assert blender_main(["scripts/capture_blender.py", "--out", "out.json"]) == 2
    assert BLENDER_CAPTURE_EXAMPLE in capsys.readouterr().err
    assert houdini_main(["scripts/capture_houdini.py", "--node", "/obj/geo1/OUT", "--out", "out.json"]) == 2
    assert HOUDINI_CAPTURE_EXAMPLE in capsys.readouterr().err
    assert blender_main(["scripts/capture_blender.py", "--help"]) == 0
    assert "--out" in capsys.readouterr().out


def test_nodebridge_scatter_report_classifies_scatter_as_equivalent() -> None:
    parsed = parse_translation_report(
        Path("fixtures/nodebridge_scatter/expected_report_houdini.txt").read_text(encoding="utf-8")
    )
    assert parsed["counts"] == {"EXACT": 10, "EQUIVALENT": 9, "APPROXIMATE": 2, "UNSUPPORTED": 0}
    link = load_link(Path("fixtures/nodebridge_scatter/link.json"))
    assert link["fidelity_class"] == "EQUIVALENT"
    assert link["operation_kind"] == "SCATTER"
    assert link["audited_commit"] == "21d5ca9cc43f09ac173a5e487003f6bc13ac33bf"


def test_unreal_adapter_refuses() -> None:
    try:
        capture_unreal()
    except HostError as exc:
        assert "v0.1" in str(exc)
        assert "docs/unreal_v0.2.md" in str(exc)
    else:
        raise AssertionError("Unreal capture must not succeed in v0.1")


class _Vec:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.x, self.y, self.z = x, y, z


class _Matrix:
    def __init__(self) -> None:
        self.rows = [[1.0, 0.0, 0.0, 1.0], [0.0, 1.0, 0.0, 2.0], [0.0, 0.0, 1.0, 3.0], [0.0, 0.0, 0.0, 1.0]]

    def __iter__(self):
        return iter(self.rows)


class _Mesh:
    def __init__(self) -> None:
        self.vertices = [
            type("V", (), {"co": _Vec(-1, -1, 0)})(),
            type("V", (), {"co": _Vec(1, -1, 0)})(),
            type("V", (), {"co": _Vec(1, 1, 0)})(),
            type("V", (), {"co": _Vec(-1, 1, 0)})(),
        ]
        self.polygons = [type("P", (), {"vertices": [0, 1, 2, 3]})()]
        self.attributes = [
            type(
                "A",
                (),
                {
                    "name": "mask",
                    "domain": "POINT",
                    "data_type": "FLOAT",
                    "data": [
                        type("D", (), {"value": 0.25})(),
                        type("D", (), {"value": 0.75})(),
                        type("D", (), {"value": 0.5})(),
                        type("D", (), {"value": 1.0})(),
                    ],
                },
            )()
        ]


class _Object:
    name = "Plane"
    type = "MESH"
    matrix_world = _Matrix()
    mesh = _Mesh()

    def evaluated_get(self, _depsgraph):
        return self

    def to_mesh(self, **_kwargs):
        return self.mesh

    def to_mesh_clear(self) -> None:
        return None


def test_fake_bpy_capture_roundtrip(tmp_path: Path) -> None:
    scene = type(
        "Scene",
        (),
        {
            "name": "Scene",
            "objects": [_Object()],
            "frame_current": 1,
            "render": type("R", (), {"fps": 24})(),
            "unit_settings": type("U", (), {"scale_length": 1.0})(),
        },
    )()
    depsgraph = type("D", (), {"object_instances": []})()
    context = type(
        "C",
        (),
        {
            "scene": scene,
            "view_layer": type("VL", (), {"update": staticmethod(lambda: None)})(),
            "evaluated_depsgraph_get": lambda self: depsgraph,
        },
    )()
    bpy = type(
        "Bpy",
        (),
        {"app": type("App", (), {"version": (4, 5, 14), "version_string": "4.5.14"})(), "context": context},
    )()
    args = type("A", (), {"objects": None, "seed": 7, "scene": None})()
    document = capture_bpy(bpy, args)
    path = tmp_path / "blender.snapshot.json"
    from parityforge.snapshot_io import save_snapshot

    save_snapshot(path, document)
    loaded = load_snapshot(path)
    assert loaded.model.identity.source_version == "4.5.14"
    assert loaded.model.identity.seed == 7
    assert loaded.objects[0].points.shape == (4, 3)
    assert loaded.objects[0].attributes[0].name == "mask"
    assert loaded.objects[0].correspondence == "none"
    old = type("Bpy", (), {"app": type("App", (), {"version": (3, 3, 0)})(), "context": context})()
    try:
        capture_bpy(old, args)
    except HostError as exc:
        assert "3.6" in str(exc)
    else:
        raise AssertionError("old Blender must be rejected")


def test_fake_hou_capture_reads_points_and_attributes(tmp_path: Path) -> None:
    class AttribData:
        Float = "Float"
        Int = "Int"

    class PrimType:
        Polygon = "Polygon"
        PackedPrim = "PackedPrim"

    class Point:
        def __init__(self, position):
            self._position = position

        def position(self):
            return self._position

    class PointRef:
        def __init__(self, number):
            self._number = number

        def number(self):
            return self._number

    class Vertex:
        def __init__(self, number):
            self._number = number

        def point(self):
            return PointRef(self._number)

    class Prim:
        def type(self):
            return PrimType.Polygon

        def vertices(self):
            return [Vertex(0), Vertex(1), Vertex(2)]

    class Attrib:
        def name(self):
            return "mask"

        def dataType(self):
            return AttribData.Float

        def size(self):
            return 1

    class PositionAttrib:
        def name(self):
            return "P"

        def dataType(self):
            return AttribData.Float

        def size(self):
            return 3

    class Geometry:
        def points(self):
            return [Point((0, 0, 0)), Point((1, 0, 0)), Point((1, 0, 1))]

        def prims(self):
            return [Prim()]

        def pointAttribs(self):
            return [PositionAttrib(), Attrib()]

        def primAttribs(self):
            return []

        def pointFloatAttribValues(self, name):
            assert name == "mask"
            return (0.1, 0.2, 0.3)

        def pointIntAttribValues(self, name):
            raise AssertionError(name)

    class Matrix:
        def asTuple(self):
            return (1, 0, 0, 0, 0, 1, 0, 2, 0, 0, 1, 0, 0, 0, 0, 1)

    class GeoNode:
        def type(self):
            return type("T", (), {"name": lambda self: "geo"})()

        def path(self):
            return "/obj/geo1"

        def worldTransform(self):
            return Matrix()

        def parent(self):
            return None

    class Node:
        def geometry(self):
            return Geometry()

        def name(self):
            return "OUT"

        def path(self):
            return "/obj/geo1/OUT"

        def type(self):
            return type("T", (), {"name": lambda self: "null"})()

        def parent(self):
            return GeoNode()

    class Hou:
        attribData = AttribData
        primType = PrimType

        def applicationVersion(self):
            return (20, 5, 332)

        def applicationVersionString(self):
            return "20.5.332"

        def frame(self):
            return 1

        def fps(self):
            return 24

        def node(self, path):
            return Node() if path == "/obj/geo1/OUT" else None

    args = type("A", (), {"hip": None, "node": "/obj/geo1/OUT", "seed": 3, "meters_per_unit": 0.01})()
    document = capture_hou(Hou(), args)
    assert document["identity"]["source_version"] == "20.5.332"
    assert document["identity"]["units"]["meters_per_unit"] == 0.01
    assert document["objects"][0]["geometry"]["point_count"] == 3
    assert document["objects"][0]["attributes"][0]["name"] == "mask"
    path = tmp_path / "houdini.snapshot.json"
    from parityforge.snapshot_io import save_snapshot

    save_snapshot(path, document)
    loaded = load_snapshot(path)
    assert np.allclose(loaded.objects[0].transform[0], [1, 0, 0, 0])
    assert loaded.objects[0].transform[1][3] == 2
