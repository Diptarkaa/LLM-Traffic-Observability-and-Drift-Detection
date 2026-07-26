from __future__ import annotations

from typing import Any

import numpy as np

# Mirrors detector/detector/distance.py. Kept as a small, independent copy
# rather than a cross-package import since dashboard/ and detector/ are
# separate deployable units with their own dependency sets (dashboard has no
# reason to depend on detector's package, and vice versa).
_EPSILON = 1e-6


def diag_mahalanobis(x: np.ndarray, centroid: np.ndarray, variance: np.ndarray) -> float:
    diff = x - centroid
    return float(np.sqrt(np.sum((diff * diff) / (variance + _EPSILON))))


def nearest_cluster_distance(x: np.ndarray, clusters: list[dict[str, Any]]) -> float:
    """Distance from x to whichever of several normal sub-clusters it's closest to.
    See detector/detector/distance.py's version for the full rationale."""
    return min(diag_mahalanobis(x, c["centroid"], c["variance"]) for c in clusters)
