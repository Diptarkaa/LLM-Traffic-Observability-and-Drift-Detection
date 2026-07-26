from __future__ import annotations

from typing import Any

import numpy as np

# Floor added to variance before dividing, so a dimension that happens to be
# ~constant in the baseline sample can't produce a divide-by-zero / blow-up.
_EPSILON = 1e-6


def diag_mahalanobis(x: np.ndarray, centroid: np.ndarray, variance: np.ndarray) -> float:
    """Distance from x to centroid, normalized per-dimension by variance.

    This is the diagonal-covariance simplification of Mahalanobis distance:
    same "distance divided by spread" idea, but using only the covariance
    diagonal instead of the full 768x768 matrix, which would need inverting
    and is unstable to estimate from a baseline of only a few thousand
    samples in 768 dimensions.
    """
    diff = x - centroid
    return float(np.sqrt(np.sum((diff * diff) / (variance + _EPSILON))))


def batch_diag_mahalanobis(vectors: np.ndarray, centroid: np.ndarray, variance: np.ndarray) -> np.ndarray:
    diff = vectors - centroid
    return np.sqrt(np.sum((diff * diff) / (variance + _EPSILON), axis=1))


def nearest_cluster_distance(x: np.ndarray, clusters: list[dict[str, Any]]) -> tuple[float, int]:
    """Distance from x to whichever of several normal sub-clusters it's closest to.

    A single centroid assumes normal traffic is one blob; if it's actually
    several distinct-but-legitimate topic clusters, the single centroid sits
    in the empty space between them and a legitimate topic switch can look
    "far" for the wrong reason. Scoring against the nearest cluster instead
    means a message only needs to resemble *some* normal cluster, not the
    blended average of all of them.
    """
    best_distance = float("inf")
    best_cluster_id = -1
    for c in clusters:
        d = diag_mahalanobis(x, c["centroid"], c["variance"])
        if d < best_distance:
            best_distance = d
            best_cluster_id = c["cluster_id"]
    return best_distance, best_cluster_id


def batch_nearest_cluster_distances(vectors: np.ndarray, clusters: list[dict[str, Any]]) -> np.ndarray:
    """Vectorized nearest_cluster_distance: one distance per row in `vectors`."""
    per_cluster = np.stack(
        [batch_diag_mahalanobis(vectors, c["centroid"], c["variance"]) for c in clusters],
        axis=1,
    )  # shape (n_vectors, n_clusters)
    return per_cluster.min(axis=1)
