# agentic-protection
This repo hosts the code for the exploration and PoC of protection and observability of agentic traffic.

## Week 4 Additions (Embeddings + Similarity)

- Kafka consumer: `consumer/`
- pgvector migration: `consumer/migrations/001_init_pgvector.sql`
- Synthetic generator: `data/synth_generator.py`
- Query CLI: `scripts/query.py`

Model in use: `nomic-ai/nomic-embed-text-v1` via sentence-transformers.

Quick docs: `docs/week4-embeddings.md`

## Week 5 Additions (Drift Detector + Dashboard)

- Drift detector: `detector/` (cron-style baseline + online scoring jobs)
- Dashboard: `dashboard/` (Streamlit: topic clusters, anomaly timeline, session drill-down)

Run with `make up` then `make generate && make publish`, or `make dashboard-demo` for the full flow. Dashboard at http://localhost:8501.

Quick docs: `docs/week5-drift-dashboard.md`
