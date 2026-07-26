#!/usr/bin/env python3
"""Manually check whether a single prompt would be flagged as drift.

Runs the same two checks the detector's online job runs -- distance to the
nearest normal baseline cluster, and similarity to permanently remembered
drift examples -- without publishing anything through Kafka or waiting for
the online job's 30s cycle.

    docker compose exec consumer python scripts/check_prompt.py --text "..."
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from pgvector.utils import Vector
from sentence_transformers import SentenceTransformer

DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/agentic")
MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "nomic-ai/nomic-embed-text-v1")
# Must match detector/detector/config.py's default so this check reflects
# what the real detector would actually decide.
MEMORY_THRESHOLD = float(os.getenv("DRIFT_MEMORY_SIMILARITY_THRESHOLD", "0.9"))

_EPSILON = 1e-6


def diag_mahalanobis(x: np.ndarray, centroid: np.ndarray, variance: np.ndarray) -> float:
    diff = x - centroid
    return float(np.sqrt(np.sum((diff * diff) / (variance + _EPSILON))))


def embed(model: SentenceTransformer, text: str) -> np.ndarray:
    vec = model.encode([f"search_query: {text}"], normalize_embeddings=True, show_progress_bar=False)[0]
    return vec.astype(np.float64)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether a prompt would be flagged as drift")
    parser.add_argument("--text", required=True, help="Prompt text to check")
    parser.add_argument("--route", default="/llm", help="Route to check the statistical baseline against")
    args = parser.parse_args()

    model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
    embedding = embed(model, args.text)

    with psycopg.connect(DSN) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute("select threshold from route_baselines where route = %s", (args.route,))
            row = cur.fetchone()
            if row is None:
                print(f"No baseline exists yet for route={args.route!r} -- run `make up` and wait for the detector's first pass.")
                return
            threshold = row[0]

            cur.execute(
                "select cluster_id, centroid, variance from route_baseline_clusters "
                "where route = %s order by cluster_id",
                (args.route,),
            )
            clusters = [
                {
                    "cluster_id": r[0],
                    "centroid": np.array(r[1], dtype=np.float64),
                    "variance": np.array(r[2], dtype=np.float64),
                }
                for r in cur.fetchall()
            ]
            best_distance = min(diag_mahalanobis(embedding, c["centroid"], c["variance"]) for c in clusters)

            # Memory check is deliberately not filtered by route -- see
            # detector/migrations/003_known_drift_memory.sql for why.
            cur.execute("SET hnsw.ef_search = 100")
            vec = Vector(embedding.tolist())
            cur.execute(
                "select 1 - (embedding <=> %s::vector) as similarity, prompt_text "
                "from known_drift_embeddings order by embedding <=> %s::vector limit 1",
                (vec, vec),
            )
            mem_row = cur.fetchone()

    is_baseline_hit = best_distance > threshold
    if mem_row is not None:
        similarity, matched_text = mem_row
        is_memory_hit = similarity >= MEMORY_THRESHOLD
    else:
        similarity, matched_text = None, None
        is_memory_hit = False

    print(f"Prompt: {args.text!r}")
    print()
    print(
        f"[baseline]  distance={best_distance:.4f}  threshold={threshold:.4f}  "
        f"{'FLAGGED' if is_baseline_hit else 'ok'}"
    )
    if similarity is not None:
        print(
            f"[memory]    similarity={similarity:.4f}  threshold={MEMORY_THRESHOLD:.4f}  "
            f"{'FLAGGED' if is_memory_hit else 'ok'}  (nearest match: {matched_text!r})"
        )
    else:
        print("[memory]    known_drift_embeddings is empty -- nothing to compare against yet")
    print()

    if is_baseline_hit or is_memory_hit:
        flagged_by = "both" if (is_baseline_hit and is_memory_hit) else ("baseline" if is_baseline_hit else "memory")
        print(f"VERDICT: would be flagged as drift (flagged_by={flagged_by})")
    else:
        print("VERDICT: would NOT be flagged")


if __name__ == "__main__":
    main()
