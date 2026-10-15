from __future__ import annotations

import numpy as np

from parityforge.coordinates import NAMED_TO_CANONICAL, change_of_basis, validate_basis
from parityforge.errors import SchemaError
from parityforge.metrics import numeric_limit
from parityforge.models import ToleranceSpec


def test_blender_negative_y_maps_to_houdini_positive_z() -> None:
    mapped = change_of_basis("blender", "houdini") @ np.array([0.0, -1.0, 0.0])
    assert np.allclose(mapped, [0.0, 0.0, 1.0])


def test_houdini_basis_matches_documented_inverse() -> None:
    assert np.allclose(
        NAMED_TO_CANONICAL["houdini"],
        [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]],
    )
    assert np.isclose(np.linalg.det(NAMED_TO_CANONICAL["houdini"]), 1.0)


def test_unreal_basis_is_left_handed_and_flips_y() -> None:
    matrix = NAMED_TO_CANONICAL["unreal"]
    assert np.isclose(np.linalg.det(matrix), -1.0)
    assert np.allclose(change_of_basis("blender", "unreal") @ np.array([1.0, 2.0, 3.0]), [1.0, -2.0, 3.0])


def test_non_unit_scale_is_not_inside_the_basis() -> None:
    try:
        validate_basis(
            name="custom_cm",
            handedness="right",
            up_axis="Z",
            forward_axis="-Y",
            matrix_to_canonical=np.eye(3) * 100.0,
        )
    except SchemaError as exc:
        assert "meters_per_unit" in str(exc)
    else:
        raise AssertionError("a scaled basis must be rejected")


def test_named_houdini_matrix_cannot_silently_differ() -> None:
    wrong = np.eye(3)
    try:
        validate_basis(
            name="houdini",
            handedness="right",
            up_axis="Y",
            forward_axis="+Z",
            matrix_to_canonical=wrong,
        )
    except SchemaError as exc:
        assert "built-in" in str(exc)
    else:
        raise AssertionError("a mislabeled Houdini basis must be rejected")


def test_tolerance_exact_threshold_fail_and_inconclusive() -> None:
    tight = ToleranceSpec(absolute=1e-3, relative=0.0, unit="meter", minimum_samples=1)
    status, _limit, exact, threshold = numeric_limit(0.0, 1.0, 4, tight)
    assert (status, exact, threshold) == ("PASS", True, False)
    status, _limit, exact, threshold = numeric_limit(5e-4, 1.0, 4, tight)
    assert (status, exact, threshold) == ("PASS", False, True)
    status, _limit, exact, threshold = numeric_limit(0.4, 1.0, 4, tight)
    assert status == "FAIL"
    assert exact is False
    loose_count = ToleranceSpec(absolute=1.0, relative=0.0, unit="meter", minimum_samples=100)
    status, _limit, exact, _threshold = numeric_limit(0.0, 1.0, 5, loose_count)
    assert status == "INCONCLUSIVE"
    assert exact is None


def test_relative_tolerance() -> None:
    relative = ToleranceSpec(absolute=0.0, relative=0.01, unit="meter", minimum_samples=1)
    status, limit, _exact, _threshold = numeric_limit(0.05, 10.0, 2, relative)
    assert status == "PASS"
    assert limit == 0.1
    status, _limit, _exact, _threshold = numeric_limit(0.2, 10.0, 2, relative)
    assert status == "FAIL"
