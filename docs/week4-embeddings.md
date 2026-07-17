# Week 4: Embeddings + Semantic Query Pipeline

## Objective Covered
- Kafka consumer writes raw events to PostgreSQL.
- Prompt and completion embeddings are generated separately using `nomic-ai/nomic-embed-text-v1`.
- Embeddings are stored in pgvector with metadata (request_id, ts, route, session_id).
- Batch size is configurable and defaults to 32 for CPU throughput.
- Synthetic 7-day dataset (~10k events) is reproducible.
- Query CLI validates nearest-neighbor search and cluster detectability.

## Components Added
- `consumer/` Python package
- `consumer/migrations/001_init_pgvector.sql`
- `data/synth_generator.py`
- `scripts/query.py`

## Run End-to-End (local)

From repo root:

```bash
# 1) Start infra + bridge + consumer
docker compose up -d --build postgres redpanda kafka-bridge consumer

# 2) Generate synthetic dataset (~10k events)
python3 data/synth_generator.py --cycles 5000 --seed 42 --out data/synth_events.jsonl

# 3) Publish synthetic events to kafka topic via bridge
python3 - <<'PY'
import json
from urllib import request

url = "http://localhost:8082/events"
with open("data/synth_events.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        payload = line.encode("utf-8")
        req = request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        request.urlopen(req, timeout=5).read()
print("published synth events")
PY

# 4) Verify rows landed in postgres
docker compose exec postgres psql -U postgres -d agentic -c "select count(*) from events_raw;"

# 5) scripts/query.py needs the same deps as the consumer package (psycopg,
#    pgvector, sentence-transformers, scikit-learn). Set up a local venv once:
make venv
source .venv/bin/activate

# 6) Run nearest-neighbor query
POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/agentic python3 scripts/query.py nearest-prompts --text "how do i optimize sql indexes" --k 10

# 7) Run cluster-size check
POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/agentic python3 scripts/query.py cluster-sizes --k 8 --limit 5000
```

Alternatively, skip the local venv and run both queries inside the consumer
container instead (it already has all deps baked in) via `make query-nearest`
/ `make query-clusters`, or `docker compose exec consumer python scripts/query.py ...`.

## Notes
- Current implementation is CPU-first and batches embeddings at 32.
- GPU acceleration is intentionally deferred.
- Consumer commits Kafka offsets only after DB commit to avoid losing acknowledged-but-not-persisted events.
