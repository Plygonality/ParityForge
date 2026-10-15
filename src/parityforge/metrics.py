"""Type-specific metric primitives. No DCC imports."""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import wasserstein_distance

from .models import ToleranceSpec

Array = np.ndarray


def numeric_limit(delta: float, scale: float, samples: int, tolerance: ToleranceSpec) -> tuple[str, float, bool | None, bool | None]:
    """Return status, limit, exact, threshold_pass.

    ``INCONCLUSIVE`` when the sample count is below the tolerance's minimum.
    That result is never reported as a pass.
    """
    limit = float(tolerance.absolute) + float(tolerance.relative) * abs(float(scale))
    if samples < tolerance.minimum_samples:
        return "INCONCLUSIVE", limit, None, None
    if abs(delta) <= limit + 1e-15:
        exact = abs(delta) <= 1e-9
        return "PASS", limit, exact, not exact
    return "FAIL", limit, False, False


def polygon_area(points: Array, faces: list[list[int]]) -> float:
    """Fan triangulation. Area uses the absolute cross product, so winding does not matter."""
    total = 0.0
    pts = np.asarray(points, dtype=float)
    for face in faces:
        if len(face) < 3:
            continue
        origin = pts[face[0]]
        for index in range(1, len(face) - 1):
            edge_a = pts[face[index]] - origin
            edge_b = pts[face[index + 1]] - origin
            total += 0.5 * float(np.linalg.norm(np.cross(edge_a, edge_b)))
    return total


def cross_distances(source: Array, target: Array) -> Array:
    """Distance from each source point to its nearest target point."""
    if len(source) == 0 or len(target) == 0:
        return np.zeros(0)
    distances, _ = cKDTree(np.asarray(target, dtype=float)).query(np.asarray(source, dtype=float), k=1)
    return np.atleast_1d(np.asarray(distances, dtype=float))


def symmetric_cross_distances(a: Array, b: Array) -> Array:
    return np.concatenate([cross_distances(a, b), cross_distances(b, a)])


def within_cloud_nn(points: Array) -> Array | None:
    if len(points) < 2:
        return None
    distances, _ = cKDTree(np.asarray(points, dtype=float)).query(points, k=2)
    return np.asarray(distances, dtype=float)[:, 1]


def density_total_variation(a: Array, b: Array, *, bins: int = 8) -> tuple[float, int, list[int]]:
    """Total variation between spatial histograms on the union bounds.

    Flat clouds drop axes whose extent is negligible. The histogram is a
    distributional comparison: it does not pair individual points.
    """
    stacked = np.vstack([np.asarray(a, dtype=float), np.asarray(b, dtype=float)])
    low = stacked.min(axis=0)
    high = stacked.max(axis=0)
    extent = high - low
    scale = float(max(extent.max(), 1.0))
    axes = [axis for axis in range(3) if extent[axis] > 1e-8 * scale]
    if not axes:
        axes = [0]
    # Keep the maximum point inside the last bin.
    pad = np.array([1e-9] * 3)
    high = high + pad
    ranges = [(float(low[axis]), float(high[axis])) for axis in axes]
    per_axis = 4 if len(axes) == 3 else bins
    hist_a, _ = np.histogramdd(np.asarray(a, dtype=float)[:, axes], bins=per_axis, range=ranges)
    hist_b, _ = np.histogramdd(np.asarray(b, dtype=float)[:, axes], bins=per_axis, range=ranges)
    total_a = float(hist_a.sum())
    total_b = float(hist_b.sum())
    if total_a == 0 or total_b == 0:
        return 1.0, len(axes), [per_axis] * len(axes)
    probability_a = hist_a / total_a
    probability_b = hist_b / total_b
    variation = 0.5 * float(np.abs(probability_a - probability_b).sum())
    return variation, len(axes), [per_axis] * len(axes)


def nn_wasserstein(a: Array, b: Array) -> float | None:
    left = within_cloud_nn(a)
    right = within_cloud_nn(b)
    if left is None or right is None:
        return None
    return float(wasserstein_distance(left, right))


def percentile(values: Array, q: float) -> float:
    if len(values) == 0:
        return float("nan")
    return float(np.percentile(values, q))
