#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from collections import Counter

import numpy as np
import psycopg
from pgvector.utils import Vector
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer
from sklearn.cluster import MiniBatchKMeans


def dsn() -> str:
    return os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/agentic")


def model_name() -> str:
    return os.getenv("EMBED_MODEL_NAME", "nomic-ai/nomic-embed-text-v1")


def embed_query(text: str) -> list[float]:
    model = SentenceTransformer(model_name(), trust_remote_code=True)
    vec = model.encode([f"search_query: {text}"], normalize_embeddings=True, show_progress_bar=False)[0]
    return vec.astype(float).tolist()


def nearest_prompts(query_text: str, k: int) -> None:
    qv = Vector(embed_query(query_text))

    with psycopg.connect(dsn()) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            # Default ivfflat.probes=1 only scans the single nearest list; with
            # lists=100 over a few thousand rows that's too coarse and can miss
            # minority cohorts (e.g. drift) entirely. Widen the search.
            cur.execute("SET ivfflat.probes = 10")
            cur.execute(
                """
                SELECT request_id, kafka_ts, route, session_id, cohort,
                       LEFT(prompt_text, 200) AS prompt_preview,
                       1 - (prompt_embedding <=> %s::vector) AS similarity
                FROM events_raw
                WHERE prompt_embedding IS NOT NULL
                ORDER BY prompt_embedding <=> %s::vector
                LIMIT %s
                """,
                (qv, qv, k),
            )
            rows = cur.fetchall()

    print(f"Nearest prompts to: {query_text!r}\n")
    for i, row in enumerate(rows, start=1):
        req_id, ts, route, session_id, cohort, prompt_preview, sim = row
        print(f"{i:02d}. sim={sim:.4f} cohort={cohort} request_id={req_id} route={route} session={session_id} ts={ts}")
        print(f"    {prompt_preview}")


def cluster_sizes(n_clusters: int, limit: int) -> None:
    with psycopg.connect(dsn()) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT prompt_embedding, cohort
                FROM events_raw
                WHERE prompt_embedding IS NOT NULL
                ORDER BY kafka_ts DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()

    if not rows:
        print("No prompt embeddings found.")
        return

    vectors = np.array([np.array(r[0], dtype=np.float32) for r in rows])
    cohorts = [r[1] for r in rows]

    km = MiniBatchKMeans(n_clusters=n_clusters, random_state=42, batch_size=256, n_init="auto")
    labels = km.fit_predict(vectors)

    unique, counts = np.unique(labels, return_counts=True)
    print(f"Cluster sizes (k={n_clusters}, samples={len(vectors)}):")
    for c_id, count in sorted(zip(unique.tolist(), counts.tolist()), key=lambda x: x[1], reverse=True):
        cohort_counts = Counter(cohorts[i] for i in range(len(labels)) if labels[i] == c_id)
        breakdown = ", ".join(f"{name}={n}" for name, n in cohort_counts.most_common())
        print(f"- cluster_{c_id}: {count} ({breakdown})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic query CLI for pgvector-backed events")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_near = sub.add_parser("nearest-prompts", help="Find nearest prompts to a query string")
    p_near.add_argument("--text", required=True, help="Query text")
    p_near.add_argument("--k", type=int, default=10, help="Top-K matches")

    p_cluster = sub.add_parser("cluster-sizes", help="Show semantic cluster sizes")
    p_cluster.add_argument("--k", type=int, default=8, help="Number of clusters")
    p_cluster.add_argument("--limit", type=int, default=5000, help="Number of recent samples")

    args = parser.parse_args()

    if args.cmd == "nearest-prompts":
        nearest_prompts(args.text, args.k)
    elif args.cmd == "cluster-sizes":
        cluster_sizes(args.k, args.limit)


if __name__ == "__main__":
    main()
