"""Declared coordinate bases and unit scales.

The canonical comparison frame is right-handed, Z-up, meters. Named bases
follow the geometry conventions used by NodeBridge (audited commit
21d5ca9cc43f09ac173a5e487003f6bc13ac33bf):

* Blender: right-handed, Z-up, forward -Y. Identity.
* Houdini: right-handed, Y-up. ``(x, y, z)`` in Blender becomes
  ``(x, z, -y)`` in Houdini, so Blender's -Y forward lands on Houdini +Z.
  That is a geometry basis, not Houdini's camera look direction.
* Unreal: left-handed, Z-up. ``(x, y, z)`` in Blender becomes ``(x, -y, z)``.
  Centimeters belong in ``meters_per_unit`` (0.01), not in the basis matrix.

Scale and axis changes are applied only from values declared on the snapshot.
Nothing in this module estimates a rigid alignment from the geometry.
"""

from __future__ import annotations

import numpy as np

from .errors import SchemaError

Array = np.ndarray

_BLENDER = np.eye(3)
# v_canonical = M @ v_houdini, with canonical == Blender.
# Inverse of NodeBridge's Blender->Houdini map (x, y, z) -> (x, z, -y).
_HOUDINI = np.array(
    [
        [1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0],
        [0.0, 1.0, 0.0],
    ]
)
# Unreal basis is a reflection and equals its own inverse.
_UNREAL = np.array(
    [
        [1.0, 0.0, 0.0],
        [0.0, -1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
)

NAMED_TO_CANONICAL: dict[str, Array] = {
    "blender": _BLENDER,
    "houdini": _HOUDINI,
    "unreal": _UNREAL,
}
ALIASES = {
    "blender": "blender",
    "blender_z_up": "blender",
    "houdini": "houdini",
    "houdini_y_up": "houdini",
    "unreal": "unreal",
    "unreal_z_up": "unreal",
}
NAMED_UP = {"blender": "Z", "houdini": "Y", "unreal": "Z"}
NAMED_FORWARD = {"blender": "-Y", "houdini": "+Z", "unreal": "+Y"}
NAMED_HANDEDNESS = {"blender": "right", "houdini": "right", "unreal": "left"}


def canonical_name(name: str) -> str | None:
    return ALIASES.get(name)


def change_of_basis(source: str, target: str) -> Array:
    """Matrix mapping vectors expressed in ``source`` into ``target``.

    Both names are canonical system names (``blender``, ``houdini``, ``unreal``),
    not aliases. Orthogonal bases satisfy ``R^{-1} = R.T`` for reflections too.
    """
    if source not in NAMED_TO_CANONICAL or target not in NAMED_TO_CANONICAL:
        raise SchemaError(
            f"Unknown named basis pair {source!r} -> {target!r}.",
            hint="Use blender, houdini, or unreal, or supply matrix_to_canonical.",
        )
    source_to_canonical = NAMED_TO_CANONICAL[source]
    target_to_canonical = NAMED_TO_CANONICAL[target]
    return target_to_canonical.T @ source_to_canonical


def validate_basis(
    *,
    name: str,
    handedness: str,
    up_axis: str,
    forward_axis: str,
    matrix_to_canonical: list[list[float]] | Array,
) -> Array:
    """Return a 3x3 float matrix, or raise when the declaration contradicts itself."""
    matrix = np.asarray(matrix_to_canonical, dtype=float)
    if matrix.shape != (3, 3):
        raise SchemaError(
            f"coordinate basis {name!r} matrix_to_canonical must be 3x3, got shape {matrix.shape}.",
            hint="Store three rows of three numbers. The matrix maps source vectors into the canonical Z-up meter frame.",
        )
    if not np.all(np.isfinite(matrix)):
        raise SchemaError(f"coordinate basis {name!r} contains a non-finite matrix entry.")
    determinant = float(np.linalg.det(matrix))
    if abs(abs(determinant) - 1.0) > 1e-6:
        raise SchemaError(
            f"coordinate basis {name!r} has determinant {determinant:.6g}. "
            "A basis matrix must be a rotation or reflection (determinant +1 or -1).",
            hint="Put unit scale in units.meters_per_unit, not in the basis matrix.",
        )
    expected_sign = 1.0 if handedness == "right" else -1.0
    if abs(determinant - expected_sign) > 1e-6:
        raise SchemaError(
            f"coordinate basis {name!r} declares handedness {handedness!r} but the "
            f"matrix determinant is {determinant:.6g}.",
            hint="Right-handed bases have determinant +1 relative to the canonical frame. Left-handed bases have -1.",
        )
    known = canonical_name(name)
    if known is not None:
        expected = NAMED_TO_CANONICAL[known]
        if not np.allclose(matrix, expected, atol=1e-9):
            raise SchemaError(
                f"coordinate basis {name!r} does not match the built-in {known} matrix.",
                hint=f"Expected matrix_to_canonical {expected.tolist()}. Refusing a different conversion under this name.",
            )
        if up_axis != NAMED_UP[known]:
            raise SchemaError(
                f"coordinate basis {name!r} declares up_axis {up_axis!r}; the {known} basis is {NAMED_UP[known]}-up."
            )
        if forward_axis != NAMED_FORWARD[known]:
            raise SchemaError(
                f"coordinate basis {name!r} declares forward_axis {forward_axis!r}; "
                f"the documented {known} forward axis is {NAMED_FORWARD[known]}."
            )
        if handedness != NAMED_HANDEDNESS[known]:
            raise SchemaError(
                f"coordinate basis {name!r} declares handedness {handedness!r}; "
                f"the {known} basis is {NAMED_HANDEDNESS[known]}-handed."
            )
    return matrix


def length_to_meters(values: Array, meters_per_unit: float) -> Array:
    if meters_per_unit <= 0:
        raise SchemaError(
            f"meters_per_unit must be positive, got {meters_per_unit}.",
            hint="Blender meters use 1. Unreal centimeters use 0.01.",
        )
    return np.asarray(values, dtype=float) * float(meters_per_unit)


def apply_linear(points: Array, matrix: Array) -> Array:
    """Apply a 3x3 matrix to row-stacked points: ``p' = M @ p``."""
    return np.asarray(points, dtype=float) @ np.asarray(matrix, dtype=float).T


def affine_world(points: Array, matrix4: Array) -> Array:
    """Apply a row-major 4x4 affine matrix to row-stacked local points."""
    matrix = np.asarray(matrix4, dtype=float)
    if matrix.shape != (4, 4):
        raise SchemaError(f"transform matrix must be 4x4, got shape {matrix.shape}.")
    if not np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1e-8):
        raise SchemaError(
            "transform matrix is not affine (last row must be [0, 0, 0, 1]).",
            hint="Store the world matrix as four rows. Translation occupies the last column.",
        )
    homo = np.concatenate([np.asarray(points, dtype=float), np.ones((len(points), 1))], axis=1)
    world = homo @ matrix.T
    return world[:, :3]


def canonical_linear_and_translation(
    matrix4: Array, basis_to_canonical: Array, meters_per_unit: float
) -> tuple[Array, Array]:
    """Map a source-frame affine matrix into canonical meters.

    Local and world lengths both scale by ``meters_per_unit``, so relative
    scale stays in the linear 3x3. Translation picks up the unit scale.
    ``A_c = R @ A @ R.T``, ``t_c = meters_per_unit * R @ t``.
    """
    matrix = np.asarray(matrix4, dtype=float)
    linear = matrix[:3, :3]
    translation = matrix[:3, 3]
    rotation = np.asarray(basis_to_canonical, dtype=float)
    canonical_linear = rotation @ linear @ rotation.T
    canonical_translation = float(meters_per_unit) * (rotation @ translation)
    return canonical_linear, canonical_translation


def points_to_canonical(
    points: Array,
    *,
    matrix4: Array | None,
    space: str,
    basis_to_canonical: Array,
    meters_per_unit: float,
) -> Array:
    """Local or world source points -> canonical world meters. No fitting."""
    pts = np.asarray(points, dtype=float)
    if pts.size == 0:
        return pts.reshape(0, 3)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise SchemaError(f"points must have shape (N, 3), got {pts.shape}.")
    if space == "local":
        if matrix4 is None:
            raise SchemaError("local points require a transform matrix.")
        pts = affine_world(pts, matrix4)
    elif space != "world":
        raise SchemaError(f"geometry space must be 'local' or 'world', got {space!r}.")
    pts = length_to_meters(pts, meters_per_unit)
    return apply_linear(pts, basis_to_canonical)


def column_scales(linear: Array) -> Array:
    """Per-axis scale as the column norms of a linear map."""
    return np.linalg.norm(np.asarray(linear, dtype=float), axis=0)


def rotation_from_linear(linear: Array) -> Array:
    """Polar rotation. A reflection in the basis is preserved (det may be -1)."""
    matrix = np.asarray(linear, dtype=float)
    left, _singular, right = np.linalg.svd(matrix)
    rotation = left @ right
    return rotation


def rotation_angle_degrees(a: Array, b: Array) -> float:
    """Geodesic angle in degrees between two rotation matrices."""
    relative = np.asarray(a, dtype=float).T @ np.asarray(b, dtype=float)
    trace = float(np.trace(relative))
    cosine = max(-1.0, min(1.0, (trace - 1.0) / 2.0))
    return float(np.degrees(np.arccos(cosine)))
