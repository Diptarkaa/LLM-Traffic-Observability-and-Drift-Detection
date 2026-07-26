from __future__ import annotations

import logging

import numpy as np
from sklearn.cluster import MiniBatchKMeans

from .config import Settings
from .db import DriftStore
from .distance import batch_nearest_cluster_distances

log = logging.getLogger("detector.baseline")

_MIN_BASELINE_SAMPLES = 30

# A cluster fit from too few points is a worse "normal" reference than no
# sub-clustering at all -- this caps how many clusters we'll actually fit,
# regardless of cfg.n_clusters, so every cluster gets a reasonable sample.
_MIN_SAMPLES_PER_CLUSTER = 30


def _fit_clusters(vectors: np.ndarray, n_clusters: int) -> list[dict]:
    """Split baseline vectors into n_clusters normal sub-clusters (see
    migrations/002_multi_cluster_baseline.sql for why one centroid isn't
    enough). Falls back to a single cluster (the old behavior) if there
    isn't enough data to support more than one reliably.
    """
    n_clusters = max(1, min(n_clusters, vectors.shape[0] // _MIN_SAMPLES_PER_CLUSTER))

    if n_clusters == 1:
        labels = np.zeros(vectors.shape[0], dtype=int)
    else:
        km = MiniBatchKMeans(n_clusters=n_clusters, random_state=42, batch_size=256, n_init="auto")
        labels = km.fit_predict(vectors)

    clusters = []
    for cluster_id in range(n_clusters):
        cluster_vectors = vectors[labels == cluster_id]
        if cluster_vectors.shape[0] == 0:
            continue
        clusters.append(
            {
                "cluster_id": cluster_id,
                "centroid": cluster_vectors.mean(axis=0),
                "variance": cluster_vectors.var(axis=0),
                "sample_count": cluster_vectors.shape[0],
            }
        )
    return clusters


def compute_baselines(store: DriftStore, cfg: Settings) -> int:
    """Returns the number of routes a baseline was (re)computed for."""
    routes = store.distinct_routes()
    if not routes:
        log.info("no routes with embeddings yet, skipping baseline computation")
        return 0

    computed = 0
    for route in routes:
        time_range = store.time_range(route)
        if time_range is None:
            continue
        start, end = time_range
        window_end = start + (end - start) * cfg.baseline_fraction

        vectors = store.fetch_embeddings(route, start, window_end)
        if vectors.shape[0] < _MIN_BASELINE_SAMPLES:
            log.info("route=%s only %d baseline samples, skipping (need >=%d)", route, vectors.shape[0], _MIN_BASELINE_SAMPLES)
            continue

        clusters = _fit_clusters(vectors, cfg.n_clusters)

        # Establish "normal spread" from every baseline point's distance to
        # its OWN nearest cluster (not one global centroid), then flag
        # anything beyond mean + N*std of that -- same control-chart idea as
        # before, just measured against nearest-cluster distance.
        self_distances = batch_nearest_cluster_distances(vectors, clusters)
        threshold = float(self_distances.mean() + cfg.sigma_multiplier * self_distances.std())

        store.upsert_baseline(
            route=route,
            clusters=clusters,
            threshold=threshold,
            sample_count=vectors.shape[0],
            window_start=start,
            window_end=window_end,
        )
        log.info(
            "baseline updated route=%s samples=%d n_clusters=%d threshold=%.4f window=[%s, %s]",
            route, vectors.shape[0], len(clusters), threshold, start, window_end,
        )
        computed += 1

    return computed
