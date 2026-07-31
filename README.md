# LLM Traffic Observatory: Semantic Logging & Drift Detection

A proof-of-concept observability pipeline for Large Language Model (LLM) traffic that captures requests and responses at the gateway, generates semantic embeddings, detects anomalous behavioral drift, and provides an interactive dashboard for monitoring and investigation.

## Overview

Modern LLM applications lack semantic observability into prompt and response traffic, making it difficult to identify evolving attack patterns, prompt injections, or abnormal usage trends. This project addresses that gap by building an asynchronous semantic analytics pipeline that operates independently of the request path.

The system captures LLM traffic using Envoy AI Gateway, streams events through Kafka, generates vector embeddings using Sentence Transformers, stores them in PostgreSQL with pgvector, and continuously analyzes semantic behavior to identify anomalous sessions.

## Key Features

- Semantic capture of LLM request and response traffic
- Asynchronous event streaming using Kafka / Redpanda
- Batched embedding generation using Sentence Transformers
- Vector storage and similarity search with PostgreSQL + pgvector
- Statistical drift detection using Mahalanobis distance
- Historical semantic memory for identifying repeated attack patterns
- Interactive Streamlit dashboard for visualization and analysis
- Fully containerized deployment using Docker Compose

## Architecture and Workflow

Traffic is captured downstream of the Envoy gateway's ext_proc inspection layer via an asynchronous HTTP bridge, decoupling capture from the real-time request path entirely — a sidecar or downstream outage never blocks user traffic. Captured events are published to a Kafka/Redpanda event bus with at-least-once delivery semantics. A Python consumer reads this stream, embeds every prompt and completion using nomic-embed-text, and persists both raw events and embeddings to PostgreSQL with pgvector, indexed via HNSW for incremental, production-safe similarity search.

A drift detector runs two independent, parallel detection signals: a statistical branch computing diagonal Mahalanobis distance against per-route baselines modeled as multiple k-means sub-clusters (rather than a single centroid, to accommodate multi-modal normal traffic); and a historical branch that permanently retains confirmed-attack embeddings and matches new traffic against them via nearest-neighbor similarity, independent of baseline recompute timing. Detected anomalies are written to a dedicated events table and surfaced through a Streamlit dashboard covering topic clustering, an anomaly timeline, and per-session drill-down.

The full stack — event bus, storage, detection, and dashboard — deploys as a single Docker Compose stack.

## Tech Stack

- Envoy AI Gateway
- Lua Filters
- Python
- Kafka / Redpanda
- PostgreSQL + pgvector
- Sentence Transformers
- Streamlit
- Docker & Docker Compose

## Repository Structure

```
consumer/          Kafka consumer and embedding pipeline
dashboard/         Streamlit observability dashboard
detector/          Drift detection and anomaly scoring
data/              Synthetic dataset generation
scripts/           Utility and query tools
docs/              Project documentation
```
