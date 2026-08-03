# agentic-protection

A proof-of-concept for protecting and observing agentic/LLM traffic. The project has two independent halves:

- **Inline inspection (real-time, blocking).** Envoy Gateway routes LLM traffic through an `ext_proc` gRPC sidecar (`grpc-inspection-server/`) that inspects every request/response frame and can allow, warn, or block (403) in-stream. Deployed to Kubernetes via the Helm chart in `helm/` — see [`helm/README.md`](helm/README.md).
- **Offline analytics pipeline (detection, not blocking).** Every frame is also mirrored asynchronously to Kafka, consumed into Postgres/pgvector with semantic embeddings, scored for drift (prompt-injection-style behavior that doesn't look like normal traffic), and surfaced on a Streamlit dashboard. This half runs entirely via `docker compose` and is what the quickstart below sets up.

These two halves are connected one-way (gateway → Kafka). Drift detection is a dashboard signal today — it does not yet feed back into the gateway's live block/allow decision.

For current known limitations and suggested next steps, see [`docs/handoff.md`](docs/handoff.md).

## Architecture at a glance

```
Client -> Envoy Gateway -> grpc-inspection-server (ext_proc) -> LLM backend
                                    |
                                    | async, fail-open, sampled
                                    v
                              kafka-bridge -> Redpanda -> consumer -> Postgres/pgvector
                                                                          |
                                                                          v
                                                              detector (baseline + online scoring)
                                                                          |
                                                                          v
                                                                 Streamlit dashboard
```

## Prerequisites (analytics pipeline quickstart)

- Docker + Docker Compose v2 (`docker compose version`)
- Python 3.10+ (stdlib only for the generator/publisher scripts — no venv needed for those two)
- ~2GB free disk for model weights and container images. First `docker compose up` build pulls `pgvector/pgvector:pg17`, `redpandadata/redpanda:v24.2.8`, and builds the consumer image, which downloads the `nomic-ai/nomic-embed-text-v1` embedding model on first run — this step is the slowest part of a fresh setup.

The inline-inspection half additionally needs a Kubernetes cluster with [Envoy Gateway](https://gateway.envoyproxy.io/) and [Envoy AI Gateway](https://aigateway.envoyproxy.io/) installed — see [`helm/README.md`](helm/README.md) for that path; it is not required for the quickstart below.

## Quickstart: reproduce the full analytics pipeline locally

One-shot version:

```bash
make dashboard-demo
```

This starts the stack, generates and publishes the synthetic 7-day/10k-event dataset, waits for ingestion and the detector's first baseline + scoring pass, runs the automated acceptance check, and opens the dashboard at http://localhost:8501.

Or step by step, so you can see what each stage actually does:

```bash
# 1. Start postgres, redpanda, kafka-bridge, consumer, detector, dashboard
make up

# 2. Generate a synthetic 7-day dataset (~10k events; 72% normal / 18% drift / 10% noise)
make generate

# 3. Publish it into Kafka via the bridge
make publish

# 4. Wait for the consumer to finish embedding + writing everything to Postgres
make wait-ingestion

# 5. Confirm no events were lost (row count should reach 10000)
make verify

# 6. Wait for the detector's first baseline computation and first scoring pass after it
make wait-baseline

# 7. Automated pass/fail check for the drift-detector acceptance criteria
make drift-acceptance

# 8. Open the dashboard
make open-dashboard
```

Useful follow-ups once the stack is running:

```bash
make query-nearest TEXT="how do i optimize sql indexes"   # semantic nearest-neighbor search
make query-clusters                                        # unsupervised cluster sizes + cohort breakdown
make drift-events                                           # eyeball what the detector has flagged
make detector-logs                                          # tail the baseline/online scoring job output
make reset                                                  # danger: drops the postgres volume, wipes all data

# Instant drift verdict for one prompt, without waiting for the online job's cycle:
docker compose exec consumer python scripts/check_prompt.py --text "ignore all previous instructions"

# Send one prompt through the real capture pipeline (Kafka -> consumer -> detector -> dashboard):
python3 scripts/send_live_prompt.py --text "..."
```

## Repository layout

| Path | What it is |
|---|---|
| `grpc-inspection-server/` | Go `ext_proc` gRPC inspector for Envoy (inline path) |
| `sidecar/kafka-bridge/` | Python FastAPI service bridging ext_proc frames to Kafka |
| `consumer/` | Kafka consumer: writes raw events to Postgres, embeds prompts/completions into pgvector |
| `detector/` | Cron-style drift detector: nightly baseline + continuous online scoring |
| `dashboard/` | Streamlit app: topic clusters, anomaly timeline, session drill-down |
| `data/synth_generator.py` | Synthetic 7-day dataset generator (normal / drift / noise cohorts) |
| `scripts/` | CLIs for publishing, querying, and validating the pipeline |
| `helm/`, `k8s-deployment/` | Kubernetes deployment for the inline-inspection half |
| `h2cll/`, `sse-echo-server/` | Synthetic demo LLM backends used to exercise the gateway path |
| `docs/` | Design docs and acceptance-criteria writeups per milestone |

## Deeper documentation

- [`docs/week4-embeddings.md`](docs/week4-embeddings.md) — Kafka → pgvector embeddings pipeline, HNSW indexing decisions, migration ledger design
- [`docs/week5-drift-dashboard.md`](docs/week5-drift-dashboard.md) — drift detector design decisions, measured recall/false-positive tradeoffs, known limitations
- [`docs/kafka-integration.md`](docs/kafka-integration.md) — capture bridge design and fail-open guarantees
- [`docs/perf.md`](docs/perf.md) — latency-overhead benchmark template and acceptance bar
- [`helm/README.md`](helm/README.md) — Kubernetes deployment for the gateway/inspection half
- [`docs/handoff.md`](docs/handoff.md) — current known limitations and next steps
