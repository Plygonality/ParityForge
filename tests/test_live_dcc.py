"""Live DCC lanes. Absent hosts are skipped and reported as NOT_RUN."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from parityforge.compare import compare_loaded
from parityforge.config import load_config
from parityforge.snapshot_io import load_snapshot


def _blender() -> str | None:
    env = os.environ.get("PARITYFORGE_BLENDER")
    if env and Path(env).is_file():
        return env
    return shutil.which("blender")


def _hython() -> str | None:
    env = os.environ.get("PARITYFORGE_HYTHON")
    if env and Path(env).is_file():
        return env
    found = shutil.which("hython")
    if found:
        return found
    hfs = os.environ.get("HFS")
    if hfs and (Path(hfs) / "bin" / "hython").is_file():
        return str(Path(hfs) / "bin" / "hython")
    return None


def test_live_blender_plane_matches_canonical_houdini(tmp_path: Path) -> None:
    blender = _blender()
    if blender is None:
        if os.environ.get("PARITYFORGE_REQUIRE_BLENDER") == "1":
            pytest.fail("Blender lane was required but no blender executable was found.")
        pytest.skip("Blender lane NOT_RUN")
    out = tmp_path / "live.snapshot.json"
    script = Path("scripts/blender_demo.py").resolve()
    completed = subprocess.run(
        [blender, "--background", "--factory-startup", "--python", str(script), "--", "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    combined = completed.stdout + "\n" + completed.stderr
    # Blender can exit 0 after an uncaught exception in --python. The snapshot
    # and the absence of a traceback are the success signals.
    assert "Traceback (most recent call last)" not in combined, combined
    assert completed.returncode == 0, combined
    assert out.is_file(), combined
    live = load_snapshot(out)
    assert live.model.identity.source_app == "blender"
    assert live.model.identity.source_version != "fixture"
    assert live.objects[0].name == "Plane"
    assert len(live.objects[0].points) == 4
    config_path = tmp_path / "live.toml"
    config_path.write_text(
        "\n".join(
            [
                'schema_version = "1.0.0"',
                'intent = "identity"',
                "[gates]",
                'ids = ["point_count", "face_count", "centroid", "surface_area", "hausdorff", "bounds"]',
                "",
                "[tolerances.hausdorff]",
                "absolute = 1e-5",
                'unit = "meter"',
                "minimum_samples = 1",
                "",
                "[tolerances.centroid]",
                "absolute = 1e-5",
                'unit = "meter"',
                "minimum_samples = 1",
                "",
                "[tolerances.surface_area]",
                "absolute = 1e-5",
                "relative = 0.0",
                'unit = "meter^2"',
                "minimum_samples = 1",
                "",
                "[tolerances.bounds]",
                "absolute = 1e-5",
                'unit = "meter"',
                "minimum_samples = 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    report = compare_loaded(
        live,
        load_snapshot(Path("fixtures/transformed_primitive/houdini.snapshot.json")),
        load_config(config_path),
        config_source=str(config_path),
    )
    assert report["overall"] == "PASS", report["summary"]
    centroid = next(item for item in report["metrics"] if item["id"].endswith("centroid"))
    assert centroid["value"]["baseline"] == [1.0, 2.0, 3.0]
    assert centroid["value"]["magnitude_m"] == 0.0
    area = next(item for item in report["metrics"] if item["id"].endswith("surface_area"))
    assert area["value"]["baseline_m2"] == 8.0
    # The capture declares no index correspondence, so vertex identity stays unevaluated.
    vertex = next(item for item in report["metrics"] if item["id"].endswith("vertex_position"))
    assert vertex["status"] == "NOT_EVALUATED"
    default = compare_loaded(
        live,
        load_snapshot(Path("fixtures/transformed_primitive/houdini.snapshot.json")),
        load_config(Path("fixtures/transformed_primitive/parityforge.toml")),
    )
    assert default["overall"] == "INCONCLUSIVE", default["summary"]
    parameters = next(item for item in default["metrics"] if item["id"] == "parameters")
    assert parameters["status"] == "PASS", parameters
    schema = next(item for item in default["metrics"] if item["id"].endswith("attribute_schema"))
    assert schema["applicable"] is False
    warning_text = " ".join(live.model.execution.warnings)
    assert "position" in warning_text
    assert "sharp_face" in warning_text or "UVMap" in warning_text


def test_live_houdini_demo(tmp_path: Path) -> None:
    hython = _hython()
    if hython is None:
        if os.environ.get("PARITYFORGE_REQUIRE_HOUDINI") == "1":
            pytest.fail("Houdini lane was required but hython was not found.")
        pytest.skip("Houdini lane NOT_RUN")
    out = tmp_path / "houdini.snapshot.json"
    script = Path("scripts/houdini_demo.py").resolve()
    completed = subprocess.run(
        [hython, str(script), "--out", str(out)],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
    loaded = load_snapshot(out)
    assert loaded.model.identity.source_app == "houdini"
    assert loaded.objects[0].points is not None
    assert len(loaded.objects[0].points) > 0
