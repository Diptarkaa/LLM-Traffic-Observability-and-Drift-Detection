-- All time-windowing here uses (event_json->>'timestamp')::timestamptz --
-- the event-time assigned when the event was captured (or, for the
-- synthetic dataset, the generator's simulated 7-day spread) -- not
-- events_raw.kafka_ts, which is when the message was actually produced to
-- Kafka. Standard event-time-vs-processing-time distinction: kafka_ts stays
-- the trustworthy ingestion-order column for everything Week 3/4 already
-- relies on; event-time is what makes the drift baseline/online split and
-- the dashboard's "7 days" timeline mean anything, since a synthetic replay
-- (or any batched backfill) publishes everything in a tight real-time burst
-- regardless of how spread out the events' own timestamps are.
--
-- Per-route baseline: mean embedding (centroid) + per-dimension variance,
-- computed by the nightly job from historical "settled" traffic.
--
-- Full Mahalanobis distance needs an invertible 768x768 covariance matrix,
-- which is unstable to estimate from a few thousand baseline samples per
-- route (classic small-n, large-d problem). We store only the diagonal
-- (per-dimension variance) and use that for a normalized-distance score --
-- the same "distance divided by spread" idea Mahalanobis is built on,
-- without the matrix-inversion instability.
CREATE TABLE IF NOT EXISTS route_baselines (
  route TEXT PRIMARY KEY,
  sample_count INT NOT NULL,
  centroid VECTOR(768) NOT NULL,
  variance DOUBLE PRECISION[] NOT NULL,
  threshold DOUBLE PRECISION NOT NULL,
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One row per session flagged by the online job. Score is the session's
-- worst (max) per-turn distance from its route's baseline -- max rather than
-- mean, because a "drift" session by design looks normal for most of its
-- turns and only pivots to anomalous content partway through; averaging
-- would dilute exactly the signal we're trying to catch.
CREATE TABLE IF NOT EXISTS drift_events (
  id BIGSERIAL PRIMARY KEY,
  session_id TEXT NOT NULL,
  route TEXT NOT NULL,
  worst_request_id TEXT NOT NULL,
  worst_event_ts TIMESTAMPTZ NOT NULL,
  worst_prompt_text TEXT,
  cohort TEXT,
  distance DOUBLE PRECISION NOT NULL,
  threshold DOUBLE PRECISION NOT NULL,
  turn_count INT NOT NULL,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (session_id)
);

CREATE INDEX IF NOT EXISTS idx_drift_events_worst_event_ts ON drift_events (worst_event_ts DESC);
CREATE INDEX IF NOT EXISTS idx_drift_events_session ON drift_events (session_id);

-- Precomputed 2D projection (UMAP) + cluster assignment for the dashboard's
-- topic-cluster page. UMAP over the full corpus is too slow to run on every
-- page load, so this is computed once (by the dashboard, on first use) and
-- persisted here -- subsequent loads are a plain SELECT.
CREATE TABLE IF NOT EXISTS prompt_projections (
  request_id TEXT PRIMARY KEY,
  x DOUBLE PRECISION NOT NULL,
  y DOUBLE PRECISION NOT NULL,
  cluster_id INT NOT NULL,
  cohort TEXT,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
