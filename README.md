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
