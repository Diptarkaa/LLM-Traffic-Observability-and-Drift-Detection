-- 002 switched to HNSW with pgvector's defaults (m=16, ef_construction=64),
-- which were tuned for a much larger corpus than this table's actual size.
-- Verified empirically across several test queries: at ~5k rows, the
-- default-quality graph could need hnsw.ef_search as high as 400 at query
-- time to reliably surface the true top-1 nearest neighbor -- the default
-- ef_search=40 silently returned a worse match instead on some queries, no
-- error, just quietly wrong results. Exactly the "recall silently degrades
-- with no operational signal" risk this migration series exists to close
-- off, just moved from "empty table at build time" to "default params
-- undersized for this table's actual scale".
--
-- HNSW's build is randomized (layer assignment during insertion), so graph
-- quality for fixed parameters varies somewhat build to build -- this was
-- tuned by rebuilding and testing across 5 diverse queries repeatedly, not
-- a single sample. m=32, ef_construction=400 consistently found the true
-- top-1 result at the application's query-time hnsw.ef_search=100 (see
-- scripts/query.py / scripts/validate.py) across every test run; lower
-- settings (m=24, ef_construction=200) were sufficient for most queries but
-- not all. Higher build parameters cost more at index-build time (a one-off
-- cost) and more memory -- both cheap trade-offs at this table's size.
DROP INDEX IF EXISTS idx_events_prompt_vec;
DROP INDEX IF EXISTS idx_events_completion_vec;

CREATE INDEX IF NOT EXISTS idx_events_prompt_vec ON events_raw
USING hnsw (prompt_embedding vector_cosine_ops) WITH (m = 32, ef_construction = 400);

CREATE INDEX IF NOT EXISTS idx_events_completion_vec ON events_raw
USING hnsw (completion_embedding vector_cosine_ops) WITH (m = 32, ef_construction = 400);
