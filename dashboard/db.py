from __future__ import annotations

import os

import numpy as np
import pandas as pd
import psycopg
import streamlit as st
from pgvector.psycopg import register_vector
from sklearn.cluster import MiniBatchKMeans

PROJECTION_LIMIT = 5000


def dsn() -> str:
    return os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/agentic")


@st.cache_resource
def get_connection() -> psycopg.Connection:
    conn = psycopg.connect(dsn(), autocommit=True)
    register_vector(conn)
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn: psycopg.Connection) -> None:
    # Defensive: these tables are normally created by detector's migration,
    # but docker-compose's `depends_on` only waits for the container to
    # start, not for its migration to finish -- so the dashboard doesn't
    # hard-depend on detector's startup timing. Schema must stay identical
    # to detector/migrations/001_drift_detection.sql.
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS route_baselines (
              route TEXT PRIMARY KEY,
              sample_count INT NOT NULL,
              n_clusters INT NOT NULL DEFAULT 1,
              threshold DOUBLE PRECISION NOT NULL,
              window_start TIMESTAMPTZ NOT NULL,
              window_end TIMESTAMPTZ NOT NULL,
              computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS route_baseline_clusters (
              route TEXT NOT NULL,
              cluster_id INT NOT NULL,
              sample_count INT NOT NULL,
              centroid VECTOR(768) NOT NULL,
              variance DOUBLE PRECISION[] NOT NULL,
              PRIMARY KEY (route, cluster_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS drift_events (
              id BIGSERIAL PRIMARY KEY,
              session_id TEXT NOT NULL,
              route TEXT NOT NULL,
              worst_request_id TEXT NOT NULL,
              worst_event_ts TIMESTAMPTZ NOT NULL,
              worst_prompt_text TEXT,
              cohort TEXT,
              distance DOUBLE PRECISION NOT NULL,
              threshold DOUBLE PRECISION NOT NULL,
              turn_count INT NOT NULL,
              flagged_by TEXT NOT NULL DEFAULT 'baseline',
              detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (session_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_projections (
              request_id TEXT PRIMARY KEY,
              x DOUBLE PRECISION NOT NULL,
              y DOUBLE PRECISION NOT NULL,
              cluster_id INT NOT NULL,
              cohort TEXT,
              computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


@st.cache_data(ttl=30)
def summary_stats() -> dict:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("select count(*) from events_raw")
        total_events = cur.fetchone()[0]
        cur.execute("select count(distinct session_id) from events_raw")
        total_sessions = cur.fetchone()[0]
        cur.execute("select count(*) from drift_events")
        total_flagged = cur.fetchone()[0]
        cur.execute("select max(computed_at) from route_baselines")
        last_baseline = cur.fetchone()[0]
        cur.execute("select max(detected_at) from drift_events")
        last_detection = cur.fetchone()[0]
    return {
        "total_events": total_events,
        "total_sessions": total_sessions,
        "total_flagged": total_flagged,
        "last_baseline": last_baseline,
        "last_detection": last_detection,
    }


def _has_projections() -> bool:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("select count(*) from prompt_projections")
        return cur.fetchone()[0] > 0


@st.cache_data(ttl=30)
def fetch_projections() -> pd.DataFrame:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            select p.request_id, p.x, p.y, p.cluster_id, p.cohort,
                   e.session_id, e.route, LEFT(e.prompt_text, 150) as prompt_preview
            from prompt_projections p
            join events_raw e on e.request_id = p.request_id and e.frame_type = 'request_body'
            """
        )
        rows = cur.fetchall()
    return pd.DataFrame(
        rows,
        columns=["request_id", "x", "y", "cluster_id", "cohort", "session_id", "route", "prompt_preview"],
    )


def compute_and_store_projections(n_clusters: int = 8, limit: int = PROJECTION_LIMIT) -> None:
    import umap

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "select request_id, prompt_embedding, cohort from events_raw "
            "where prompt_embedding is not null order by kafka_ts desc limit %s",
            (limit,),
        )
        rows = cur.fetchall()

    if not rows:
        return

    request_ids = [r[0] for r in rows]
    vectors = np.array([np.array(r[1], dtype=np.float32) for r in rows])
    cohorts = [r[2] for r in rows]

    reducer = umap.UMAP(n_components=2, random_state=42, n_neighbors=15, min_dist=0.1)
    coords = reducer.fit_transform(vectors)

    km = MiniBatchKMeans(n_clusters=n_clusters, random_state=42, batch_size=256, n_init="auto")
    labels = km.fit_predict(vectors)

    with conn.cursor() as cur:
        cur.execute("delete from prompt_projections")
        cur.executemany(
            "insert into prompt_projections (request_id, x, y, cluster_id, cohort) values (%s, %s, %s, %s, %s)",
            [
                (request_ids[i], float(coords[i, 0]), float(coords[i, 1]), int(labels[i]), cohorts[i])
                for i in range(len(request_ids))
            ],
        )

    fetch_projections.clear()


def ensure_projections_ready(n_clusters: int = 8, limit: int = PROJECTION_LIMIT) -> bool:
    """Returns True if projections already existed, False if just computed."""
    if _has_projections():
        return True
    compute_and_store_projections(n_clusters=n_clusters, limit=limit)
    return False


@st.cache_data(ttl=30)
def fetch_drift_events() -> pd.DataFrame:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            select session_id, route, worst_request_id, worst_event_ts, worst_prompt_text,
                   cohort, distance, threshold, turn_count, flagged_by, detected_at
            from drift_events
            order by worst_event_ts asc
            """
        )
        rows = cur.fetchall()
    return pd.DataFrame(
        rows,
        columns=[
            "session_id", "route", "worst_request_id", "worst_event_ts", "worst_prompt_text",
            "cohort", "distance", "threshold", "turn_count", "flagged_by", "detected_at",
        ],
    )


@st.cache_data(ttl=30)
def fetch_all_session_ids(limit: int = 2000) -> list[str]:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "select distinct session_id from events_raw where session_id is not null order by 1 limit %s",
            (limit,),
        )
        return [r[0] for r in cur.fetchall()]


@st.cache_data(ttl=30)
def fetch_session_turns(session_id: str) -> pd.DataFrame:
    # Ordered and displayed by event-time (see note in
    # detector/migrations/001_drift_detection.sql) so the transcript reads
    # in the narrative order the synthetic generator (or a real capture)
    # intended, not by incidental Kafka-publish order.
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            select request_id, (event_json->>'timestamp')::timestamptz as event_ts,
                   frame_type, route, prompt_text, completion_text,
                   prompt_embedding, cohort, decision, blocked
            from events_raw
            where session_id = %s
            order by event_ts asc
            """,
            (session_id,),
        )
        rows = cur.fetchall()
    return pd.DataFrame(
        rows,
        columns=[
            "request_id", "event_ts", "frame_type", "route", "prompt_text", "completion_text",
            "prompt_embedding", "cohort", "decision", "blocked",
        ],
    )


@st.cache_data(ttl=30)
def fetch_baseline(route: str) -> dict | None:
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("select threshold from route_baselines where route = %s", (route,))
        row = cur.fetchone()
        if row is None:
            return None
        threshold = row[0]

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
    }
