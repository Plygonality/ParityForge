"""Offline comparison. Requires no Blender or Houdini installation."""

from __future__ import annotations

from typing import Any

import numpy as np

from .config import gates_for
from .coordinates import (
    canonical_linear_and_translation,
    column_scales,
    points_to_canonical,
    rotation_angle_degrees,
    rotation_from_linear,
)
from .metrics import (
    density_total_variation,
    nn_wasserstein,
    numeric_limit,
    percentile,
    polygon_area,
    symmetric_cross_distances,
)
from .models import CompareConfig, ToleranceSpec
from .snapshot_io import LoadedObject, LoadedSnapshot

NOTES = [
    "Declared basis matrices and meters_per_unit scales were applied.",
    "Geometry was not rigidly aligned. ICP, centroid subtraction, and scale normalisation are not used.",
    "A matching count is not an equality result.",
]


def _clean(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, np.floating | float):
        number = float(value)
        if not np.isfinite(number):
            return None
        if abs(number) < 1e-12:
            return 0.0
        return float(f"{number:.9g}")
    if isinstance(value, np.integer | int) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(item) for item in value]
    return value


def _metric(
    *,
    metric_id: str,
    status: str,
    kind: str,
    applicable: bool,
    rationale: str,
    unit: str = "",
    tolerance: dict[str, Any] | None = None,
    value: dict[str, Any] | None = None,
    exact: bool | None = None,
    threshold_pass: bool | None = None,
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "status": status,
        "kind": kind,
        "applicable": applicable,
        "gated": False,
        "unit": unit,
        "tolerance": tolerance,
        "value": _clean(value or {}),
        "rationale": rationale,
        "exact": exact,
        "threshold_pass": threshold_pass,
    }


def _tol_dict(tolerance: ToleranceSpec, limit: float | None = None) -> dict[str, Any]:
    payload = {
        "absolute": tolerance.absolute,
        "relative": tolerance.relative,
        "unit": tolerance.unit,
        "minimum_samples": tolerance.minimum_samples,
    }
    if limit is not None:
        payload["limit"] = limit
    return payload


def _structural(metric_id: str, kind: str, ok: bool, rationale: str, value: dict[str, Any]) -> dict[str, Any]:
    return _metric(
        metric_id=metric_id,
        status="PASS" if ok else "FAIL",
        kind=kind,
        applicable=True,
        rationale=rationale,
        value=value,
        exact=ok,
        threshold_pass=False,
    )


def _not_applicable(metric_id: str, kind: str, rationale: str) -> dict[str, Any]:
    return _metric(
        metric_id=metric_id,
        status="NOT_EVALUATED",
        kind=kind,
        applicable=False,
        rationale=rationale,
    )


def _not_evaluated(metric_id: str, kind: str, rationale: str, value: dict[str, Any] | None = None) -> dict[str, Any]:
    return _metric(
        metric_id=metric_id,
        status="NOT_EVALUATED",
        kind=kind,
        applicable=True,
        rationale=rationale,
        value=value,
    )


def _numeric(
    metric_id: str,
    kind: str,
    delta: float,
    scale: float,
    samples: int,
    tolerance: ToleranceSpec,
    rationale: str,
    value: dict[str, Any],
    unit: str,
) -> dict[str, Any]:
    status, limit, exact, threshold = numeric_limit(delta, scale, samples, tolerance)
    value = dict(value)
    value["delta"] = delta
    value["limit"] = limit
    value["samples"] = samples
    return _metric(
        metric_id=metric_id,
        status=status,
        kind=kind,
        applicable=True,
        rationale=rationale,
        unit=unit or tolerance.unit,
        tolerance=_tol_dict(tolerance, limit),
        value=value,
        exact=exact,
        threshold_pass=threshold,
    )


def _basis_matrix(snapshot: LoadedSnapshot) -> np.ndarray:
    return np.asarray(snapshot.model.identity.coordinate_basis.matrix_to_canonical, dtype=float)


def _meters(snapshot: LoadedSnapshot) -> float:
    return float(snapshot.model.identity.units.meters_per_unit)


def cloud_for(obj: LoadedObject, snapshot: LoadedSnapshot, which: str) -> np.ndarray | None:
    basis = _basis_matrix(snapshot)
    meters = _meters(snapshot)
    if which == "geometry" and obj.points is not None and obj.geometry_space is not None:
        return points_to_canonical(
            obj.points,
            matrix4=obj.transform,
            space=obj.geometry_space,
            basis_to_canonical=basis,
            meters_per_unit=meters,
        )
    if which == "instances" and obj.instance_positions is not None and obj.instance_space is not None:
        return points_to_canonical(
            obj.instance_positions,
            matrix4=obj.transform,
            space=obj.instance_space,
            basis_to_canonical=basis,
            meters_per_unit=meters,
        )
    return None


def primary_cloud(obj: LoadedObject, snapshot: LoadedSnapshot) -> tuple[np.ndarray | None, str]:
    if obj.type in {"points", "instances"} and obj.instance_positions is not None:
        return cloud_for(obj, snapshot, "instances"), "instances"
    if obj.points is not None:
        return cloud_for(obj, snapshot, "geometry"), "geometry"
    if obj.instance_positions is not None:
        return cloud_for(obj, snapshot, "instances"), "instances"
    return None, "none"


def _pair_objects(baseline: LoadedSnapshot, candidate: LoadedSnapshot) -> tuple[list[tuple[LoadedObject, LoadedObject]], list[str]]:
    warnings: list[str] = []
    if len(baseline.objects) == 1 and len(candidate.objects) == 1:
        left, right = baseline.objects[0], candidate.objects[0]
        if left.name != right.name:
            warnings.append(
                f"Paired the only objects despite different names: {left.name!r} and {right.name!r}."
            )
        return [(left, right)], warnings
    by_name = {obj.name: obj for obj in candidate.objects}
    pairs: list[tuple[LoadedObject, LoadedObject]] = []
    for obj in baseline.objects:
        other = by_name.get(obj.name)
        if other is None:
            warnings.append(f"Baseline object {obj.name!r} has no same-named candidate object.")
        else:
            pairs.append((obj, other))
    baseline_names = {obj.name for obj in baseline.objects}
    for obj in candidate.objects:
        if obj.name not in baseline_names:
            warnings.append(f"Candidate object {obj.name!r} has no same-named baseline object.")
    return pairs, warnings


def _values_close(left: Any, right: Any, tolerance: float) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, int | float) and isinstance(right, int | float):
        return abs(float(left) - float(right)) <= tolerance + 1e-15
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return False
        return all(_values_close(left[key], right[key], tolerance) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_values_close(a, b, tolerance) for a, b in zip(left, right, strict=True))
    return left == right


def _parameter_delta(left: Any, right: Any) -> tuple[bool, list[str]]:
    """Return (equal_keys, mismatch descriptions) without applying tolerance."""
    if isinstance(left, dict) and isinstance(right, dict):
        missing = sorted(set(left) - set(right))
        extra = sorted(set(right) - set(left))
        notes = [f"missing on candidate: {missing}" if missing else "", f"missing on baseline: {extra}" if extra else ""]
        notes = [note for note in notes if note]
        shared = set(left) & set(right)
        ok = not missing and not extra
        for key in sorted(shared):
            child_ok, child_notes = _parameter_delta(left[key], right[key])
            ok = ok and child_ok
            notes.extend(f"{key}.{item}" if isinstance(left[key], dict) else f"{key}: {item}" for item in child_notes)
        return ok, notes
    return True, []


def _compare_parameters(prefix: str, left: dict[str, Any], right: dict[str, Any], tolerance: ToleranceSpec) -> dict[str, Any]:
    if not left and not right:
        return _not_applicable(f"{prefix}parameters", "structural", "Neither snapshot declares parameters.")
    keys_ok, notes = _parameter_delta(left, right)
    if not keys_ok:
        return _structural(
            f"{prefix}parameters",
            "structural",
            False,
            "Parameter names differ. Missing keys are a failure, not a skipped field. " + " ".join(notes),
            {"baseline": left, "candidate": right},
        )
    equal = _values_close(left, right, tolerance.absolute)
    return _structural(
        f"{prefix}parameters",
        "structural",
        equal,
        "Declared parameters compared by name. Numeric values use the absolute parameter tolerance.",
        {"baseline": left, "candidate": right, "absolute_tolerance": tolerance.absolute},
    )


def _schema_keys(obj: LoadedObject) -> list[tuple[str, str, str]]:
    return sorted((attr.name, attr.domain, attr.type) for attr in obj.attributes)


def _canonical_attribute_values(attr: Any, obj: LoadedObject, snapshot: LoadedSnapshot) -> tuple[np.ndarray | None, str]:
    values = np.asarray(attr.values)
    if attr.type in {"float", "int"} or attr.role in {"scalar", "color", "uv"}:
        return values, "values compared without unit or basis conversion"
    basis = _basis_matrix(snapshot)
    meters = _meters(snapshot)
    linear, _translation = canonical_linear_and_translation(obj.transform, basis, meters)
    scales = column_scales(linear)
    non_uniform = float(scales.max() - scales.min()) > 1e-6
    if attr.role == "unknown":
        return None, "vector role is unknown; values were not converted or compared"
    if attr.role == "direction":
        if non_uniform:
            return None, "direction attribute under non-uniform scale is inconclusive in v0.1 (no inverse-transpose)"
        return values @ basis.T, "direction vectors rotated by the declared basis; translation and unit scale were not applied"
    if attr.role == "position":
        space = obj.geometry_space or obj.instance_space or "world"
        return points_to_canonical(
            values,
            matrix4=obj.transform,
            space=space,
            basis_to_canonical=basis,
            meters_per_unit=meters,
        ), "position attribute converted with the object transform, units, and basis"
    return None, f"attribute role {attr.role!r} is not compared in v0.1"


def _compare_attribute_values(
    prefix: str,
    left: LoadedObject,
    right: LoadedObject,
    left_snap: LoadedSnapshot,
    right_snap: LoadedSnapshot,
    tolerance: ToleranceSpec,
) -> list[dict[str, Any]]:
    schema_left = set(_schema_keys(left))
    schema_right = set(_schema_keys(right))
    if schema_left != schema_right:
        return [
            _not_evaluated(
                f"{prefix}attribute_values",
                "attribute",
                "Attribute names, domains, or types differ. Values were not interpolated and were not compared.",
                {"baseline": [list(item) for item in sorted(schema_left)], "candidate": [list(item) for item in sorted(schema_right)]},
            )
        ]
    if not schema_left:
        return [_not_applicable(f"{prefix}attribute_values", "attribute", "Neither object declares attributes.")]
    results = []
    failures = 0
    inconclusive = 0
    unsupported = 0
    comparable = 0
    by_right = {(attr.name, attr.domain, attr.type): attr for attr in right.attributes}
    supported_domains = {"point", "vertex", "face", "corner", "instance", "detail"}
    for key in sorted(schema_left):
        attr_l = next(attr for attr in left.attributes if (attr.name, attr.domain, attr.type) == key)
        attr_r = by_right[key]
        metric_id = f"{prefix}attribute_value.{key[0]}.{key[1]}"
        if key[1] not in supported_domains or key[1] == "edge":
            unsupported += 1
            results.append(
                _metric(
                    metric_id=metric_id,
                    status="UNSUPPORTED",
                    kind="attribute",
                    applicable=True,
                    rationale=f"Domain {key[1]!r} values are not compared in v0.1. The attribute is still listed.",
                    value={"name": key[0], "domain": key[1], "type": key[2]},
                )
            )
            continue
        converted_l, note_l = _canonical_attribute_values(attr_l, left, left_snap)
        converted_r, note_r = _canonical_attribute_values(attr_r, right, right_snap)
        if converted_l is None or converted_r is None:
            inconclusive += 1
            results.append(
                _metric(
                    metric_id=metric_id,
                    status="INCONCLUSIVE",
                    kind="attribute",
                    applicable=True,
                    rationale=f"{note_l} {note_r}".strip(),
                    value={"name": key[0], "domain": key[1], "type": key[2]},
                )
            )
            continue
        if converted_l.shape != converted_r.shape:
            failures += 1
            results.append(
                _structural(
                    metric_id,
                    "attribute",
                    False,
                    "Attribute value lengths differ. No interpolation was applied.",
                    {"name": key[0], "baseline_shape": list(converted_l.shape), "candidate_shape": list(converted_r.shape)},
                )
            )
            continue
        if left.correspondence != "index" or right.correspondence != "index":
            if not (key[1] == "instance" and left.instance_correspondence == "index" and right.instance_correspondence == "index"):
                inconclusive += 1
                results.append(
                    _not_evaluated(
                        metric_id,
                        "attribute",
                        "Attribute values need explicit index correspondence. None was declared, so values were not paired.",
                        {"name": key[0], "domain": key[1]},
                    )
                )
                continue
        delta = float(np.max(np.abs(np.asarray(converted_l, dtype=float) - np.asarray(converted_r, dtype=float))))
        comparable += 1
        scale = float(np.max(np.abs(np.asarray(converted_l, dtype=float)))) if converted_l.size else 0.0
        item = _numeric(
            metric_id,
            "attribute",
            delta,
            scale,
            int(converted_l.shape[0]),
            tolerance,
            f"Max absolute difference after the declared conversion. {note_l}",
            {"name": key[0], "domain": key[1], "type": key[2]},
            tolerance.unit,
        )
        if item["status"] == "FAIL":
            failures += 1
        elif item["status"] == "INCONCLUSIVE":
            inconclusive += 1
        results.append(item)
    if failures:
        rollup_status, exact = "FAIL", False
        rationale = "At least one attribute value comparison failed."
    elif inconclusive:
        rollup_status, exact = "INCONCLUSIVE", None
        rationale = "At least one attribute value comparison is inconclusive."
    elif comparable == 0 and unsupported:
        rollup_status, exact = "UNSUPPORTED", None
        rationale = "Every declared attribute uses a domain v0.1 does not score."
    else:
        rollup_status, exact = "PASS", True
        rationale = "Comparable attribute values are within tolerance."
    results.insert(
        0,
        _metric(
            metric_id=f"{prefix}attribute_values",
            status=rollup_status,
            kind="attribute",
            applicable=True,
            rationale=rationale,
            value={"comparable": comparable, "failed": failures, "unsupported": unsupported},
            exact=exact if rollup_status == "PASS" else False if rollup_status == "FAIL" else None,
            threshold_pass=False if rollup_status == "PASS" else None,
        ),
    )
    return results


def _compare_clouds(
    prefix: str,
    label: str,
    left: np.ndarray,
    right: np.ndarray,
    left_obj: LoadedObject,
    right_obj: LoadedObject,
    config: CompareConfig,
) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    samples = min(len(left), len(right))
    centroid_l = left.mean(axis=0) if len(left) else None
    centroid_r = right.mean(axis=0) if len(right) else None
    if centroid_l is None or centroid_r is None:
        metrics.append(_not_applicable(f"{prefix}centroid", "numerical", f"No {label} points to locate a centroid."))
    else:
        delta_vec = centroid_r - centroid_l
        magnitude = float(np.linalg.norm(delta_vec))
        scale = float(max(np.linalg.norm(centroid_l), np.linalg.norm(centroid_r)))
        metrics.append(
            _numeric(
                f"{prefix}centroid",
                "numerical",
                magnitude,
                scale,
                samples,
                config.tolerances["centroid"],
                "Magnitude of the canonical world centroid difference, in meters. "
                "The scenes were not recentered before this subtraction.",
                {
                    "baseline": centroid_l,
                    "candidate": centroid_r,
                    "delta_vector_m": delta_vec,
                    "magnitude_m": magnitude,
                    "cloud": label,
                },
                "meter",
            )
        )
    if len(left) and len(right):
        min_l, max_l = left.min(0), left.max(0)
        min_r, max_r = right.min(0), right.max(0)
        bounds_delta = float(max(np.max(np.abs(min_l - min_r)), np.max(np.abs(max_l - max_r))))
        extent_l = max_l - min_l
        extent_r = max_r - min_r
        extent_delta = float(np.max(np.abs(extent_l - extent_r)))
        scale = float(max(np.max(np.abs(np.vstack([min_l, max_l, min_r, max_r]))), 1e-12))
        metrics.append(
            _numeric(
                f"{prefix}bounds",
                "numerical",
                bounds_delta,
                scale,
                samples,
                config.tolerances["bounds"],
                "Maximum absolute difference of canonical AABB minimum and maximum components.",
                {"baseline_min": min_l, "baseline_max": max_l, "candidate_min": min_r, "candidate_max": max_r},
                "meter",
            )
        )
        metrics.append(
            _numeric(
                f"{prefix}extents",
                "numerical",
                extent_delta,
                float(max(np.max(extent_l), np.max(extent_r), 1e-12)),
                samples,
                config.tolerances["extents"],
                "Maximum absolute difference of canonical AABB extents (size, not position).",
                {"baseline": extent_l, "candidate": extent_r},
                "meter",
            )
        )
        distances = symmetric_cross_distances(left, right)
        p99 = percentile(distances, 99)
        metrics.append(
            _numeric(
                f"{prefix}cross_nn_p99",
                "numerical",
                p99,
                float(np.max(extent_l)) if len(extent_l) else 0.0,
                samples,
                config.tolerances["cross_nn_p99"],
                "99th percentile of symmetric nearest-neighbour distances between the unmatched clouds. "
                "This measures discrepancy. It does not establish vertex identity.",
                {
                    "p50_m": percentile(distances, 50),
                    "p95_m": percentile(distances, 95),
                    "p99_m": p99,
                    "max_m": float(np.max(distances)) if len(distances) else None,
                    "cloud": label,
                },
                "meter",
            )
        )
        hausdorff = float(np.max(distances)) if len(distances) else 0.0
        metrics.append(
            _numeric(
                f"{prefix}hausdorff",
                "numerical",
                hausdorff,
                float(max(np.max(extent_l), 1e-12)),
                samples,
                config.tolerances["hausdorff"],
                "Symmetric Hausdorff distance (max nearest-neighbour) in canonical meters. "
                "No rigid pre-alignment.",
                {"hausdorff_m": hausdorff, "cloud": label},
                "meter",
            )
        )
        if left_obj.correspondence == "index" and right_obj.correspondence == "index" and len(left) == len(right):
            vertex_delta = float(np.max(np.linalg.norm(left - right, axis=1))) if len(left) else 0.0
            metrics.append(
                _numeric(
                    f"{prefix}vertex_position",
                    "numerical",
                    vertex_delta,
                    float(max(np.max(np.abs(left)), 1e-12)),
                    len(left),
                    config.tolerances["vertex_position"],
                    "Maximum per-index distance after canonicalization. "
                    "Index correspondence was declared on both snapshots.",
                    {"max_distance_m": vertex_delta, "count": len(left)},
                    "meter",
                )
            )
        elif len(left) != len(right):
            metrics.append(
                _structural(
                    f"{prefix}vertex_position",
                    "numerical",
                    False,
                    "Point counts differ, so index correspondence cannot be applied.",
                    {"baseline_count": len(left), "candidate_count": len(right)},
                )
            )
        else:
            metrics.append(
                _not_evaluated(
                    f"{prefix}vertex_position",
                    "numerical",
                    "No explicit vertex correspondence was declared. "
                    "Point positions were not paired by index, and matching counts were not treated as identity.",
                    {"baseline_count": len(left), "candidate_count": len(right), "correspondence": "none"},
                )
            )
        variation, axes_used, binning = density_total_variation(left, right)
        metrics.append(
            _numeric(
                f"{prefix}density_total_variation",
                "distributional",
                variation,
                1.0,
                samples,
                config.tolerances["density_total_variation"],
                "Total variation between spatial density histograms on the union bounds. "
                "A pass is statistical similarity, not instance equality.",
                {"total_variation": variation, "axes": axes_used, "bins_per_axis": binning, "cloud": label},
                "1",
            )
        )
        wasserstein = nn_wasserstein(left, right)
        if wasserstein is None:
            metrics.append(
                _metric(
                    metric_id=f"{prefix}nn_distance_wasserstein",
                    status="INCONCLUSIVE",
                    kind="distributional",
                    applicable=True,
                    rationale="Nearest-neighbour distance distributions need at least two points in each cloud.",
                    value={"samples": samples},
                    tolerance=_tol_dict(config.tolerances["nn_distance_wasserstein"]),
                )
            )
        else:
            metrics.append(
                _numeric(
                    f"{prefix}nn_distance_wasserstein",
                    "distributional",
                    wasserstein,
                    1.0,
                    samples,
                    config.tolerances["nn_distance_wasserstein"],
                    "1-Wasserstein distance between within-cloud nearest-neighbour distance distributions. "
                    "A pass is statistical similarity of the sampling pattern, not shared point positions.",
                    {"wasserstein_m": wasserstein, "cloud": label},
                    "meter",
                )
            )
    return metrics


def _compare_object(
    left: LoadedObject,
    right: LoadedObject,
    left_snap: LoadedSnapshot,
    right_snap: LoadedSnapshot,
    config: CompareConfig,
) -> list[dict[str, Any]]:
    prefix = f"{left.name}."
    metrics: list[dict[str, Any]] = []
    left_points = None if left.points is None else len(left.points)
    right_points = None if right.points is None else len(right.points)
    if left_points is None and right_points is None:
        metrics.append(_not_applicable(f"{prefix}point_count", "structural", "Neither object has a point array."))
    elif left_points is None or right_points is None:
        metrics.append(
            _structural(
                f"{prefix}point_count",
                "structural",
                False,
                "Point data is present on only one side.",
                {"baseline": left_points, "candidate": right_points},
            )
        )
    else:
        metrics.append(
            _structural(
                f"{prefix}point_count",
                "structural",
                left_points == right_points,
                "Point counts compared exactly. Equal counts are not a geometry match.",
                {"baseline": left_points, "candidate": right_points},
            )
        )
    left_faces = None if left.faces is None else len(left.faces)
    right_faces = None if right.faces is None else len(right.faces)
    if left_faces is None and right_faces is None:
        metrics.append(_not_applicable(f"{prefix}face_count", "structural", "Neither object has polygon faces."))
        metrics.append(_not_applicable(f"{prefix}topology", "structural", "Neither object has polygon faces."))
        metrics.append(_not_applicable(f"{prefix}surface_area", "numerical", "Surface area is undefined without polygon faces."))
    elif left_faces is None or right_faces is None:
        metrics.append(
            _structural(
                f"{prefix}face_count",
                "structural",
                False,
                "Polygon faces are present on only one side.",
                {"baseline": left_faces, "candidate": right_faces},
            )
        )
        metrics.append(_not_evaluated(f"{prefix}topology", "structural", "Topology was not compared because one side has no faces."))
        metrics.append(_not_evaluated(f"{prefix}surface_area", "numerical", "Surface area was not compared because one side has no faces."))
    else:
        metrics.append(
            _structural(
                f"{prefix}face_count",
                "structural",
                left_faces == right_faces,
                "Face counts compared exactly.",
                {"baseline": left_faces, "candidate": right_faces},
            )
        )
        if left.correspondence == "index" and right.correspondence == "index":
            metrics.append(
                _structural(
                    f"{prefix}topology",
                    "structural",
                    left.faces == right.faces,
                    "Face index lists compared exactly under declared index correspondence.",
                    {"baseline_faces": len(left.faces), "candidate_faces": len(right.faces)},
                )
            )
        else:
            metrics.append(
                _not_evaluated(
                    f"{prefix}topology",
                    "structural",
                    "Face topology was not compared because vertex correspondence is not declared.",
                )
            )
    if left.instance_count is None and right.instance_count is None:
        metrics.append(_not_applicable(f"{prefix}instance_count", "structural", "Neither object has instances."))
        metrics.append(_not_applicable(f"{prefix}instance_ids", "structural", "Neither object has instance ids."))
    elif left.instance_count is None or right.instance_count is None:
        metrics.append(
            _structural(
                f"{prefix}instance_count",
                "structural",
                False,
                "Instances are present on only one side.",
                {"baseline": left.instance_count, "candidate": right.instance_count},
            )
        )
        metrics.append(
            _not_evaluated(
                f"{prefix}instance_ids",
                "structural",
                "Instance ids were not compared because one side has no instances.",
            )
        )
    else:
        metrics.append(
            _structural(
                f"{prefix}instance_count",
                "structural",
                left.instance_count == right.instance_count,
                "Instance counts compared exactly. Equal counts are not an instance match.",
                {
                    "baseline": left.instance_count,
                    "candidate": right.instance_count,
                    "prototype_baseline": left.instance_prototype,
                    "prototype_candidate": right.instance_prototype,
                },
            )
        )
        if left.instance_ids is None and right.instance_ids is None:
            metrics.append(
                _not_applicable(
                    f"{prefix}instance_ids",
                    "structural",
                    "Neither instance set declares ids. Count agreement does not imply id agreement.",
                )
            )
        elif left.instance_ids is None or right.instance_ids is None:
            metrics.append(
                _structural(
                    f"{prefix}instance_ids",
                    "structural",
                    False,
                    "Instance ids are present on only one side.",
                    {},
                )
            )
        else:
            same = np.array_equal(left.instance_ids, right.instance_ids)
            metrics.append(
                _structural(
                    f"{prefix}instance_ids",
                    "structural",
                    bool(same),
                    "Instance ids compared in declared order.",
                    {"baseline_count": len(left.instance_ids), "candidate_count": len(right.instance_ids)},
                )
            )

    left_cloud, cloud_label = primary_cloud(left, left_snap)
    right_cloud, _ = primary_cloud(right, right_snap)
    if left_cloud is None or right_cloud is None:
        for name, kind in (
            ("centroid", "numerical"),
            ("bounds", "numerical"),
            ("extents", "numerical"),
            ("vertex_position", "numerical"),
            ("hausdorff", "numerical"),
            ("cross_nn_p99", "numerical"),
            ("density_total_variation", "distributional"),
            ("nn_distance_wasserstein", "distributional"),
        ):
            metrics.append(_not_applicable(f"{prefix}{name}", kind, "No primary point cloud on one or both objects."))
    else:
        metrics.extend(_compare_clouds(prefix, cloud_label, left_cloud, right_cloud, left, right, config))

    if left.faces is not None and right.faces is not None and left_cloud is not None and right_cloud is not None:
        area_l = polygon_area(left_cloud, left.faces)
        area_r = polygon_area(right_cloud, right.faces)
        delta = abs(area_l - area_r)
        metrics.append(
            _numeric(
                f"{prefix}surface_area",
                "numerical",
                delta,
                max(area_l, area_r, 1e-12),
                len(left.faces),
                config.tolerances["surface_area"],
                "Surface area of fan-triangulated polygons in canonical meters. "
                "Winding does not change the absolute area.",
                {"baseline_m2": area_l, "candidate_m2": area_r},
                "meter^2",
            )
        )

    linear_l, translation_l = canonical_linear_and_translation(left.transform, _basis_matrix(left_snap), _meters(left_snap))
    linear_r, translation_r = canonical_linear_and_translation(right.transform, _basis_matrix(right_snap), _meters(right_snap))
    translation_delta = translation_r - translation_l
    translation_mag = float(np.linalg.norm(translation_delta))
    rotation_delta = rotation_angle_degrees(rotation_from_linear(linear_l), rotation_from_linear(linear_r))
    scale_l = column_scales(linear_l)
    scale_r = column_scales(linear_r)
    scale_delta = float(np.max(np.abs(scale_l - scale_r)))
    t_metric = _numeric(
        f"{prefix}transform_translation",
        "transform",
        translation_mag,
        float(max(np.linalg.norm(translation_l), np.linalg.norm(translation_r))),
        1,
        config.tolerances["transform_translation"],
        "Canonical translation difference of the declared object matrices. Not estimated from points.",
        {"baseline_m": translation_l, "candidate_m": translation_r, "delta_vector_m": translation_delta},
        "meter",
    )
    r_metric = _numeric(
        f"{prefix}transform_rotation",
        "transform",
        rotation_delta,
        180.0,
        1,
        config.tolerances["transform_rotation"],
        "Angle between the rotational parts of the declared matrices, after the basis change.",
        {"degrees": rotation_delta},
        "degree",
    )
    s_metric = _numeric(
        f"{prefix}transform_scale",
        "transform",
        scale_delta,
        float(max(np.max(scale_l), np.max(scale_r), 1e-12)),
        1,
        config.tolerances["transform_scale"],
        "Maximum absolute difference of per-axis scales extracted from the declared matrices.",
        {"baseline": scale_l, "candidate": scale_r},
        "1",
    )
    child_status = [t_metric["status"], r_metric["status"], s_metric["status"]]
    if "FAIL" in child_status:
        rollup = "FAIL"
    elif "INCONCLUSIVE" in child_status:
        rollup = "INCONCLUSIVE"
    else:
        rollup = "PASS"
    metrics.extend(
        [
            _metric(
                metric_id=f"{prefix}transform",
                status=rollup,
                kind="transform",
                applicable=True,
                rationale="Rollup of declared translation, rotation, and scale. Point clouds are not used to derive this transform.",
                value={
                    "translation_status": t_metric["status"],
                    "rotation_status": r_metric["status"],
                    "scale_status": s_metric["status"],
                },
                exact=all(item.get("exact") for item in (t_metric, r_metric, s_metric)) if rollup == "PASS" else False,
                threshold_pass=rollup == "PASS" and not all(item.get("exact") for item in (t_metric, r_metric, s_metric)),
            ),
            t_metric,
            r_metric,
            s_metric,
        ]
    )
    schema_l = _schema_keys(left)
    schema_r = _schema_keys(right)
    if not schema_l and not schema_r:
        metrics.append(_not_applicable(f"{prefix}attribute_schema", "attribute", "Neither object declares attributes."))
    else:
        metrics.append(
            _structural(
                f"{prefix}attribute_schema",
                "attribute",
                schema_l == schema_r,
                "Attribute name, domain, and type compared exactly. "
                "A domain mismatch is a semantic failure. Values are not resampled onto the other domain.",
                {"baseline": [list(item) for item in schema_l], "candidate": [list(item) for item in schema_r]},
            )
        )
    metrics.extend(
        _compare_attribute_values(
            prefix,
            left,
            right,
            left_snap,
            right_snap,
            config.tolerances["attribute_value"],
        )
    )
    return metrics


def _mark_gates(metrics: list[dict[str, Any]], gate_ids: list[str]) -> None:
    gates = set(gate_ids)
    for item in metrics:
        tail = item["id"].split(".")[-1]
        # attribute_value.name.domain should not match a gate named "point".
        parts = item["id"].split(".")
        head = parts[1] if len(parts) > 1 else parts[0]
        item["gated"] = item["id"] in gates or head in gates or (len(parts) == 1 and tail in gates)


def _overall(metrics: list[dict[str, Any]]) -> str:
    gated = [item for item in metrics if item["gated"] and item["applicable"]]
    if not gated:
        return "INCONCLUSIVE"
    statuses = {item["status"] for item in gated}
    if "FAIL" in statuses:
        return "FAIL"
    if "INCONCLUSIVE" in statuses or "NOT_EVALUATED" in statuses:
        return "INCONCLUSIVE"
    if "UNSUPPORTED" in statuses:
        return "INCONCLUSIVE"
    if statuses == {"PASS"}:
        return "PASS"
    return "INCONCLUSIVE"


def _labels(overall: str, intent: str, metrics: list[dict[str, Any]]) -> list[str]:
    if overall != "PASS":
        return []
    gated = [item for item in metrics if item["gated"] and item["applicable"]]
    if intent == "distribution":
        return ["equivalent_in_distribution", "statistical_similarity"]
    if gated and all(item.get("exact") is True for item in gated):
        vertex = [item for item in gated if item["id"].endswith("vertex_position")]
        if vertex and all(item["status"] == "PASS" for item in vertex):
            return ["exact_match"]
    return ["within_tolerance"]


def _claim(overall: str, intent: str, labels: list[str]) -> str:
    if overall == "FAIL":
        return "not_equal"
    if overall == "INCONCLUSIVE":
        return "inconclusive"
    if overall == "UNSUPPORTED":
        return "unsupported"
    if intent == "distribution":
        return "statistical_similarity"
    if "exact_match" in labels:
        return "exact_match"
    return "within_tolerance"


def _find(metrics: list[dict[str, Any]], suffix: str) -> dict[str, Any] | None:
    for item in metrics:
        if item["id"] == suffix or item["id"].endswith("." + suffix):
            return item
    return None


def _summary(baseline: LoadedSnapshot, candidate: LoadedSnapshot, metrics: list[dict[str, Any]], overall: str, claim: str) -> str:
    b_id = baseline.model.identity
    c_id = candidate.model.identity
    sentences = [
        f"{b_id.source_app} {b_id.source_version} and {c_id.source_app} {c_id.source_version}."
    ]
    instances = _find(metrics, "instance_count")
    points = _find(metrics, "point_count")
    if instances and instances["applicable"] and "baseline" in instances["value"]:
        left = instances["value"]["baseline"]
        right = instances["value"]["candidate"]
        if left == right:
            sentences.append(f"Both generated {left} instances.")
        else:
            sentences.append(f"Baseline generated {left} instances and candidate generated {right} instances.")
    elif points and points["applicable"] and "baseline" in points["value"]:
        left = points["value"]["baseline"]
        right = points["value"]["candidate"]
        if left == right:
            sentences.append(f"Both generated {left} points.")
        else:
            sentences.append(f"Baseline generated {left} points and candidate generated {right} points.")
    centroid = _find(metrics, "centroid")
    if centroid and centroid["status"] != "NOT_EVALUATED" and "magnitude_m" in centroid["value"]:
        sentences.append(f"Canonical centroids differ by {centroid['value']['magnitude_m']} m.")
    nearest = _find(metrics, "cross_nn_p99")
    if nearest and "p99_m" in nearest["value"]:
        sentences.append(
            f"99th-percentile symmetric nearest-neighbour distance is {nearest['value']['p99_m']} m."
        )
    claim_text = {
        "statistical_similarity": "statistical similarity (equivalent in distribution)",
        "exact_match": "exact match under the declared correspondence",
        "within_tolerance": "agreement within the declared tolerances",
        "not_equal": "gated metrics do not agree",
        "inconclusive": "inconclusive",
        "unsupported": "unsupported",
    }[claim]
    sentences.append(f"Equality claim: {claim_text}.")
    sentences.append(f"Overall {overall}.")
    ungated_failures = [
        item["id"] for item in metrics if item["status"] == "FAIL" and not item["gated"] and item["applicable"]
    ]
    if ungated_failures:
        sentences.append(
            "Ungated failures remain visible: " + ", ".join(ungated_failures) + "."
        )
    return " ".join(sentences)


def compare_loaded(
    baseline: LoadedSnapshot,
    candidate: LoadedSnapshot,
    config: CompareConfig,
    *,
    config_source: str = "defaults",
) -> dict[str, Any]:
    warnings: list[str] = []
    warnings.extend(baseline.model.execution.warnings)
    warnings.extend(candidate.model.execution.warnings)
    if baseline.model.identity.scene != candidate.model.identity.scene:
        warnings.append(
            f"Scene names differ ({baseline.model.identity.scene!r} vs {candidate.model.identity.scene!r}). "
            "Scene name is not a geometry metric."
        )
    pairs, pair_warnings = _pair_objects(baseline, candidate)
    warnings.extend(pair_warnings)
    metrics: list[dict[str, Any]] = []
    metrics.append(
        _structural(
            "object_count",
            "structural",
            len(baseline.objects) == len(candidate.objects),
            "Object counts compared exactly.",
            {"baseline": len(baseline.objects), "candidate": len(candidate.objects)},
        )
    )
    paired_all = len(pairs) == len(baseline.objects) == len(candidate.objects)
    metrics.append(
        _structural(
            "object_pairing",
            "structural",
            paired_all,
            "Objects pair by name. A single object on each side is paired even when the names differ, and that rename is warned.",
            {"pairs": [[left.name, right.name] for left, right in pairs]},
        )
    )
    b_seed = baseline.model.identity.seed
    c_seed = candidate.model.identity.seed
    if b_seed is None and c_seed is None:
        metrics.append(_not_applicable("seed", "structural", "Neither snapshot declares a seed."))
    elif b_seed is None or c_seed is None:
        metrics.append(
            _structural(
                "seed",
                "structural",
                False,
                "Seed is declared on only one snapshot.",
                {"baseline": b_seed, "candidate": c_seed},
            )
        )
    else:
        metrics.append(
            _structural(
                "seed",
                "structural",
                b_seed == c_seed,
                "Declared seeds compared as integers. Equal seeds do not imply equal samples.",
                {"baseline": b_seed, "candidate": c_seed},
            )
        )
    metrics.append(
        _compare_parameters(
            "",
            baseline.model.parameters,
            candidate.model.parameters,
            config.tolerances["parameters"],
        )
    )
    for left, right in pairs:
        metrics.extend(_compare_object(left, right, baseline, candidate, config))
    metrics.append(
        _metric(
            metric_id="image",
            status="UNSUPPORTED",
            kind="image",
            applicable=True,
            rationale=(
                "Image comparison is outside the v0.1 quality gate. "
                "Matched-camera screenshots may be linked, and renderer differences are not scored."
            ),
            value={"thumbnail_baseline": baseline.model.execution.thumbnail, "thumbnail_candidate": candidate.model.execution.thumbnail},
        )
    )
    gate_ids = gates_for(config)
    _mark_gates(metrics, gate_ids)
    overall = _overall(metrics)
    labels = _labels(overall, config.intent, metrics)
    claim = _claim(overall, config.intent, labels)
    summary = _summary(baseline, candidate, metrics, overall, claim)
    return {
        "schema_version": "1.0.0",
        "parityforge": "0.1.0",
        "overall": overall,
        "intent": config.intent,
        "equality_claim": claim,
        "labels": labels,
        "summary": summary,
        "gates": gate_ids,
        "notes": list(NOTES),
        "warnings": warnings,
        "config_source": config_source,
        "baseline": {
            "path": str(baseline.path),
            "snapshot_id": baseline.model.identity.snapshot_id,
            "source_app": baseline.model.identity.source_app,
            "source_version": baseline.model.identity.source_version,
            "scene": baseline.model.identity.scene,
            "asset": baseline.model.identity.asset,
            "seed": baseline.model.identity.seed,
            "basis": baseline.model.identity.coordinate_basis.name,
            "meters_per_unit": baseline.model.identity.units.meters_per_unit,
        },
        "candidate": {
            "path": str(candidate.path),
            "snapshot_id": candidate.model.identity.snapshot_id,
            "source_app": candidate.model.identity.source_app,
            "source_version": candidate.model.identity.source_version,
            "scene": candidate.model.identity.scene,
            "asset": candidate.model.identity.asset,
            "seed": candidate.model.identity.seed,
            "basis": candidate.model.identity.coordinate_basis.name,
            "meters_per_unit": candidate.model.identity.units.meters_per_unit,
        },
        "metrics": metrics,
    }
