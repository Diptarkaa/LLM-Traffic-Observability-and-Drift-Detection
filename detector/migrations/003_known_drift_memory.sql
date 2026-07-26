-- The statistical baseline (route_baseline_clusters) answers "does this look
-- different from history" -- but that answer depends on the baseline's
-- current shape, which shifts on every nightly recompute. Once a specific
-- prompt has actually been confirmed as drift, we want to remember it
-- permanently and catch any repeat (or close paraphrase) of it immediately,
-- on ANY route, independent of what the baseline currently looks like or
-- when it last recomputed.
--
-- Deliberately NOT scoped by route: an attack's phrasing doesn't care which
-- endpoint it was sent through, so a confirmed example should protect every
-- route, not just the one it was first seen on. source_route is stored only
-- as metadata for human review, never filtered on when matching.
--
-- Append-only -- the detector itself never deletes from this table.
--
-- HNSW from the start (not ivfflat): this table starts empty and grows
-- incrementally one confirmed example at a time, which is exactly the shape
-- of table ivfflat handles badly and HNSW doesn't (see consumer/migrations/
-- 002_switch_to_hnsw_index.sql for the full reasoning).
CREATE TABLE IF NOT EXISTS known_drift_embeddings (
  id BIGSERIAL PRIMARY KEY,
  source_request_id TEXT NOT NULL UNIQUE,
  source_session_id TEXT NOT NULL,
  source_route TEXT NOT NULL,
  prompt_text TEXT,
  embedding VECTOR(768) NOT NULL,
  distance DOUBLE PRECISION NOT NULL,
  added_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_known_drift_embedding ON known_drift_embeddings
USING hnsw (embedding vector_cosine_ops);

-- Records which mechanism actually caught a session, for transparency:
-- 'baseline' (statistically far from normal), 'memory' (matched a previously
-- confirmed example), or 'both'.
ALTER TABLE drift_events ADD COLUMN IF NOT EXISTS flagged_by TEXT NOT NULL DEFAULT 'baseline';
