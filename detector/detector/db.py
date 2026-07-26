from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from pgvector.utils import Vector

# Must match the identical string used by every other component that runs
# migrations against this database (see consumer/consumer/db.py) --
# hashtext() derives the advisory lock key from it, and the lock only
# serializes correctly if every caller hashes the same string.
_MIGRATION_LOCK_KEY = "agentic_protection_schema_migrations"


class DriftStore:
    def __init__(self, dsn: str):
        # autocommit so a failed statement (e.g. a transient error in one
        # scheduled job run) doesn't poison the connection for every query
        # after it -- this is a long-lived connection reused across jobs,
        # not a short-lived one wrapped in its own try/rollback each time.
        self.conn = psycopg.connect(dsn, autocommit=True)

    def close(self) -> None:
        self.conn.close()

    def run_migrations(self, migrations_dir: Path, component: str) -> None:
        # Same advisory-lock + ledger discipline as consumer/consumer/db.py
        # -- see that file's comment for the full rationale. Under
        # autocommit there's no transaction to roll back on failure, so this
        # is simpler than the consumer's version, but the lock/ledger logic
        # is identical.
        files = sorted(p for p in migrations_dir.glob("*.sql"))
        with self.conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s)::bigint)", (_MIGRATION_LOCK_KEY,))
            try:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        component TEXT NOT NULL,
                        filename TEXT NOT NULL,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (component, filename)
                    )
                    """
                )
                cur.execute("SELECT filename FROM schema_migrations WHERE component = %s", (component,))
                applied = {r[0] for r in cur.fetchall()}
                for path in files:
                    if path.name in applied:
                        continue
                    cur.execute(path.read_text())
                    cur.execute(
                        "INSERT INTO schema_migrations (component, filename) VALUES (%s, %s)",
                        (component, path.name),
                    )
            finally:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s)::bigint)", (_MIGRATION_LOCK_KEY,))
        register_vector(self.conn)

    def distinct_routes(self) -> list[str]:
        with self.conn.cursor() as cur:
            cur.execute(
                "select distinct route from events_raw "
                "where route is not null and prompt_embedding is not null"
            )
            return [r[0] for r in cur.fetchall()]

    def total_embedding_count(self, route: str) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                "select count(*) from events_raw where route = %s and prompt_embedding is not null",
                (route,),
            )
            return cur.fetchone()[0]

    def time_range(self, route: str) -> tuple[datetime, datetime] | None:
        # event-time (event_json->>'timestamp'), not kafka_ts -- see the note
        # at the top of migrations/001_drift_detection.sql for why.
        with self.conn.cursor() as cur:
            cur.execute(
                "select min((event_json->>'timestamp')::timestamptz), "
                "       max((event_json->>'timestamp')::timestamptz) "
                "from events_raw where route = %s and prompt_embedding is not null",
                (route,),
            )
            row = cur.fetchone()
            if row is None or row[0] is None:
                return None
            return row[0], row[1]

    def fetch_embeddings(self, route: str, start: datetime, end: datetime) -> np.ndarray:
        with self.conn.cursor() as cur:
            cur.execute(
                "select prompt_embedding from events_raw "
                "where route = %s and prompt_embedding is not null "
                "and (event_json->>'timestamp')::timestamptz >= %s "
                "and (event_json->>'timestamp')::timestamptz <= %s",
                (route, start, end),
            )
            rows = cur.fetchall()
        if not rows:
            return np.empty((0, 0))
        return np.array([np.array(r[0], dtype=np.float64) for r in rows])

    def upsert_baseline(
        self,
        route: str,
        clusters: list[dict[str, Any]],
        threshold: float,
        sample_count: int,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO route_baselines
                    (route, sample_count, n_clusters, threshold, window_start, window_end, computed_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (route) DO UPDATE SET
                    sample_count = EXCLUDED.sample_count,
                    n_clusters = EXCLUDED.n_clusters,
                    threshold = EXCLUDED.threshold,
                    window_start = EXCLUDED.window_start,
                    window_end = EXCLUDED.window_end,
                    computed_at = NOW()
                """,
                (route, sample_count, len(clusters), threshold, window_start, window_end),
            )
            # Re-fitting can change both the number of clusters and their
            # boundaries, so the old per-cluster rows for this route are
            # replaced wholesale rather than upserted by cluster_id.
            cur.execute("DELETE FROM route_baseline_clusters WHERE route = %s", (route,))
            cur.executemany(
                """
                INSERT INTO route_baseline_clusters (route, cluster_id, sample_count, centroid, variance)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (
                        route,
                        c["cluster_id"],
                        c["sample_count"],
                        Vector(c["centroid"].astype(float).tolist()),
                        list(c["variance"].astype(float)),
                    )
                    for c in clusters
                ],
            )

    def fetch_baseline(self, route: str) -> dict[str, Any] | None:
        with self.conn.cursor() as cur:
            cur.execute(
                "select threshold, window_end from route_baselines where route = %s",
                (route,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            threshold, window_end = row

            cur.execute(
                "select cluster_id, centroid, variance from route_baseline_clusters "
                "where route = %s order by cluster_id",
                (route,),
            )
            cluster_rows = cur.fetchall()

        return {
            "clusters": [
                {
                    "cluster_id": r[0],
                    "centroid": np.array(r[1], dtype=np.float64),
                    "variance": np.array(r[2], dtype=np.float64),
                }
                for r in cluster_rows
            ],
            "threshold": threshold,
            "window_end": window_end,
        }

    def fetch_online_candidates(self, route: str, since: datetime) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(
                "select session_id, request_id, (event_json->>'timestamp')::timestamptz, "
                "       prompt_text, cohort, prompt_embedding "
                "from events_raw "
                "where route = %s and prompt_embedding is not null "
                "and (event_json->>'timestamp')::timestamptz > %s "
                "order by session_id, (event_json->>'timestamp')::timestamptz",
                (route, since),
            )
            rows = cur.fetchall()
        return [
            {
                "session_id": r[0],
                "request_id": r[1],
                "event_ts": r[2],
                "prompt_text": r[3],
                "cohort": r[4],
                "embedding": np.array(r[5], dtype=np.float64),
            }
            for r in rows
        ]

    def upsert_drift_event(
        self,
        session_id: str,
        route: str,
        worst_request_id: str,
        worst_event_ts: datetime,
        worst_prompt_text: str | None,
        cohort: str | None,
        distance: float,
        threshold: float,
        turn_count: int,
        flagged_by: str,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO drift_events
                    (session_id, route, worst_request_id, worst_event_ts, worst_prompt_text,
                     cohort, distance, threshold, turn_count, flagged_by, detected_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (session_id) DO UPDATE SET
                    route = EXCLUDED.route,
                    worst_request_id = EXCLUDED.worst_request_id,
                    worst_event_ts = EXCLUDED.worst_event_ts,
                    worst_prompt_text = EXCLUDED.worst_prompt_text,
                    cohort = EXCLUDED.cohort,
                    distance = EXCLUDED.distance,
                    threshold = EXCLUDED.threshold,
                    turn_count = EXCLUDED.turn_count,
                    flagged_by = EXCLUDED.flagged_by,
                    detected_at = NOW()
                WHERE EXCLUDED.distance > drift_events.distance
                """,
                (
                    session_id,
                    route,
                    worst_request_id,
                    worst_event_ts,
                    worst_prompt_text,
                    cohort,
                    distance,
                    threshold,
                    turn_count,
                    flagged_by,
                ),
            )

    def remember_drift_embedding(
        self,
        request_id: str,
        session_id: str,
        route: str,
        prompt_text: str | None,
        embedding: np.ndarray,
        distance: float,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO known_drift_embeddings
                    (source_request_id, source_session_id, source_route, prompt_text, embedding, distance)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_request_id) DO NOTHING
                """,
                (
                    request_id,
                    session_id,
                    route,
                    prompt_text,
                    Vector(embedding.astype(float).tolist()),
                    distance,
                ),
            )

    def nearest_known_drift_similarity(self, embedding: np.ndarray) -> float | None:
        """Cosine similarity to the closest permanently-remembered drift
        example, checked globally across every route (see migrations/
        003_known_drift_memory.sql for why this is deliberately unscoped)."""
        vec = Vector(embedding.astype(float).tolist())
        with self.conn.cursor() as cur:
            cur.execute("SET hnsw.ef_search = 100")
            cur.execute(
                "select 1 - (embedding <=> %s::vector) as similarity "
                "from known_drift_embeddings order by embedding <=> %s::vector limit 1",
                (vec, vec),
            )
            row = cur.fetchone()
        return row[0] if row else None
