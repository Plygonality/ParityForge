from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from parityforge.compare import compare_loaded
from parityforge.config import load_config
from parityforge.snapshot_io import load_snapshot


def _compare(case: str) -> dict:
    root = Path("fixtures") / case
    return compare_loaded(
        load_snapshot(root / "blender.snapshot.json"),
        load_snapshot(root / "houdini.snapshot.json"),
        load_config(root / "parityforge.toml"),
    )


def _metric(report: dict, suffix: str) -> dict:
    matches = [item for item in report["metrics"] if item["id"].endswith("." + suffix) or item["id"] == suffix]
    assert matches, suffix
    return matches[0]


def test_transformed_primitive_is_an_exact_true_positive() -> None:
    report = _compare("transformed_primitive")
    assert report["overall"] == "PASS"
    assert report["equality_claim"] == "exact_match"
    centroid = _metric(report, "centroid")
    assert centroid["value"]["baseline"] == [1.0, 2.0, 3.0]
    assert centroid["value"]["magnitude_m"] == 0.0
    assert _metric(report, "surface_area")["value"]["baseline_m2"] == 8.0
    houdini = json.loads(Path("fixtures/transformed_primitive/houdini.snapshot.json").read_text(encoding="utf-8"))
    matrix = houdini["objects"][0]["transform"]["matrix"]
    assert matrix[0][3] == 100.0
    assert matrix[1][3] == 300.0
    assert matrix[2][3] == -200.0
    assert houdini["identity"]["units"]["meters_per_unit"] == 0.01


def test_incorrect_transform_fails_by_0_4_meters() -> None:
    report = _compare("incorrect_transform")
    assert report["overall"] == "FAIL"
    centroid = _metric(report, "centroid")
    assert centroid["status"] == "FAIL"
    assert centroid["value"]["delta_vector_m"] == [0.4, 0.0, 0.0]
    assert centroid["value"]["magnitude_m"] == 0.4
    assert _metric(report, "point_count")["status"] == "PASS"
    assert _metric(report, "surface_area")["status"] == "PASS"
    assert "0.4 m" in report["summary"]
    assert "accuracy" not in report["summary"].lower()


def test_scatter_is_distributional_and_not_vertex_identity() -> None:
    report = _compare("seeded_scatter")
    assert report["overall"] == "PASS"
    assert report["equality_claim"] == "statistical_similarity"
    assert "equivalent_in_distribution" in report["labels"]
    assert _metric(report, "instance_count")["value"]["baseline"] == 5000
    assert _metric(report, "vertex_position")["status"] == "NOT_EVALUATED"
    assert _metric(report, "seed")["status"] == "PASS"
    nearest = _metric(report, "cross_nn_p99")
    assert nearest["value"]["p99_m"] > 0.05
    assert nearest["gated"] is False
    assert nearest["status"] == "FAIL"
    assert "5000 instances" in report["summary"]
    assert "statistical similarity" in report["summary"]
    assert "Ungated failures" in report["summary"]


def test_attribute_domain_mismatch_is_a_semantic_failure() -> None:
    report = _compare("attribute_domain_mismatch")
    assert report["overall"] == "FAIL"
    schema = _metric(report, "attribute_schema")
    assert schema["status"] == "FAIL"
    assert ["mask", "point", "float"] in schema["value"]["baseline"]
    assert ["mask", "face", "float"] in schema["value"]["candidate"]
    values = _metric(report, "attribute_values")
    assert values["status"] == "NOT_EVALUATED"
    assert _metric(report, "point_count")["status"] == "PASS"


def test_translation_is_not_removed_before_comparison() -> None:
    """Identical local geometry with different translations must fail."""
    report = _compare("incorrect_transform")
    assert _metric(report, "transform")["status"] == "FAIL"
    assert report["notes"]
    assert any("ICP" in note for note in report["notes"])


def test_identity_without_correspondence_is_inconclusive(tmp_path: Path) -> None:
    source = json.loads(Path("fixtures/transformed_primitive/blender.snapshot.json").read_text(encoding="utf-8"))
    source["objects"][0]["geometry"]["correspondence"] = "none"
    source["identity"]["snapshot_id"] = "no-correspondence"
    left = tmp_path / "left.snapshot.json"
    right = tmp_path / "right.snapshot.json"
    # Drop the sealed hash so the writer reseals both copies.
    source.pop("hashes")
    from parityforge.snapshot_io import save_snapshot

    save_snapshot(left, source)
    source["identity"]["snapshot_id"] = "no-correspondence-b"
    save_snapshot(right, source)
    report = compare_loaded(load_snapshot(left), load_snapshot(right), load_config(Path("fixtures/parityforge.toml")))
    assert _metric(report, "vertex_position")["status"] == "NOT_EVALUATED"
    assert report["overall"] == "INCONCLUSIVE"


def test_houdini_fixture_points_are_the_hand_conversion() -> None:
    houdini = json.loads(Path("fixtures/transformed_primitive/houdini.snapshot.json").read_text(encoding="utf-8"))
    points = np.asarray(houdini["objects"][0]["geometry"]["points"], dtype=float)
    expected = np.array(
        [
            [-100.0, 0.0, 100.0],
            [100.0, 0.0, 100.0],
            [100.0, 0.0, -100.0],
            [-100.0, 0.0, -100.0],
        ]
    )
    assert np.allclose(points, expected)
