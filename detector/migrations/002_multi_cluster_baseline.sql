-- 001 modeled "normal" per route as a single centroid + diagonal variance --
-- one blob. That's a poor fit if legitimate traffic actually has several
-- distinct-but-legitimate topic clusters (e.g. coding questions vs aptitude
-- questions): the single centroid ends up sitting in the empty space between
-- them, and a legitimate switch between distant-but-valid topics can score as
-- "far from normal" for the wrong reason -- not because anything suspicious
-- happened, just because the one blended average doesn't represent either
-- topic well.
--
-- This migration replaces the single centroid with several per-route
-- sub-cluster centroids (fit via k-means over the baseline window). Online
-- scoring becomes "distance to the NEAREST normal sub-cluster" instead of
-- "distance to the one blended average" -- a legitimate message just needs to
-- be close to *some* normal cluster, not close to the average of all of them
-- combined. route_baselines keeps the route-level threshold/window metadata;
-- the per-cluster centroid/variance now lives in route_baseline_clusters,
-- one row per (route, cluster_id).
ALTER TABLE route_baselines DROP COLUMN IF EXISTS centroid;
ALTER TABLE route_baselines DROP COLUMN IF EXISTS variance;
ALTER TABLE route_baselines ADD COLUMN IF NOT EXISTS n_clusters INT NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS route_baseline_clusters (
  route TEXT NOT NULL,
  cluster_id INT NOT NULL,
  sample_count INT NOT NULL,
  centroid VECTOR(768) NOT NULL,
  variance DOUBLE PRECISION[] NOT NULL,
  PRIMARY KEY (route, cluster_id)
);
