# Consumer

Python consumer that reads capture events from Kafka, stores raw events in PostgreSQL, and stores prompt/completion embeddings in pgvector.

## Model

This project uses `nomic-ai/nomic-embed-text-v1` through sentence-transformers with `trust_remote_code=True`.

## Environment Variables

- `KAFKA_BOOTSTRAP_SERVERS` (default: `redpanda:9092`)
- `KAFKA_TOPIC` (default: `envoy.capture.events`)
- `KAFKA_GROUP_ID` (default: `agentic-consumer`)
- `POSTGRES_DSN` (default: `postgresql://postgres:postgres@postgres:5432/agentic`)
- `EMBED_MODEL_NAME` (default: `nomic-ai/nomic-embed-text-v1`)
- `EMBED_BATCH_SIZE` (default: `32`)
- `DB_BATCH_SIZE` (default: `256`)

## Run locally

```bash
cd consumer
pip install .
consumer-run
```
