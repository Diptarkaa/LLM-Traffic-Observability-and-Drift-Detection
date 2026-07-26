-- 001 built ivfflat indexes before any rows existed. ivfflat computes its
-- cluster centroids ("lists") from whatever data is present at build time --
-- building on an empty table produces a degenerate index that never
-- improves as the consumer streams rows in afterward, and nothing
-- schedules a REINDEX to fix it. That's fine for a one-shot demo bulk-load
-- (`make reset` + republish rebuilds it against real data), but wrong for
-- any deployment where the consumer runs continuously against live
-- traffic -- which is this dashboard's actual stated purpose.
--
-- HNSW has no build-order sensitivity: it's a graph structure that stays
-- well-formed as rows are added incrementally, matching how this table is
-- actually populated. Trades slightly slower inserts and more memory for
-- that property, which is the right tradeoff for a continuously-written
-- table over needing an operational reindex schedule.
DROP INDEX IF EXISTS idx_events_prompt_vec;
DROP INDEX IF EXISTS idx_events_completion_vec;

CREATE INDEX IF NOT EXISTS idx_events_prompt_vec ON events_raw
USING hnsw (prompt_embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_events_completion_vec ON events_raw
USING hnsw (completion_embedding vector_cosine_ops);
