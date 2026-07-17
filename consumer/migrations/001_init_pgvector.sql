CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS events_raw (
    --kafka metadata
  id BIGSERIAL PRIMARY KEY,
  kafka_topic TEXT NOT NULL,
  kafka_partition INT NOT NULL,
  kafka_offset BIGINT NOT NULL,
  kafka_ts TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    --event metadata
  request_id TEXT,
  route TEXT,
  session_id TEXT,
  frame_type TEXT,
  end_of_stream BOOLEAN NOT NULL DEFAULT FALSE,

    --payload
  headers JSONB NOT NULL DEFAULT '{}'::jsonb,
  body TEXT,
  body_size INT NOT NULL DEFAULT 0,

    --decision
  decision TEXT,
  blocked BOOLEAN NOT NULL DEFAULT FALSE,
  warned BOOLEAN NOT NULL DEFAULT FALSE,

    --raw event
  event_json JSONB NOT NULL,
  cohort TEXT,

    --semantic fields
  prompt_text TEXT,
  completion_text TEXT,
  prompt_embedding VECTOR(768),
  completion_embedding VECTOR(768),

  UNIQUE (kafka_topic, kafka_partition, kafka_offset)
);

CREATE INDEX IF NOT EXISTS idx_events_raw_ts ON events_raw (kafka_ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_raw_request_id ON events_raw (request_id);
CREATE INDEX IF NOT EXISTS idx_events_raw_route ON events_raw (route);
CREATE INDEX IF NOT EXISTS idx_events_raw_session_id ON events_raw (session_id);
CREATE INDEX IF NOT EXISTS idx_events_raw_cohort ON events_raw (cohort);
CREATE INDEX IF NOT EXISTS idx_events_raw_event_json_gin ON events_raw USING GIN (event_json);

-- ivfflat indexes require ANALYZE for optimal plans after data load.
CREATE INDEX IF NOT EXISTS idx_events_prompt_vec ON events_raw
USING ivfflat (prompt_embedding vector_cosine_ops) WITH (lists = 10);

CREATE INDEX IF NOT EXISTS idx_events_completion_vec ON events_raw
USING ivfflat (completion_embedding vector_cosine_ops) WITH (lists = 10);
-- lists ~= rows/1000 per pgvector's guidance; re-tune (and `make reset` to
-- rebuild) if the synthetic dataset size changes materially.
