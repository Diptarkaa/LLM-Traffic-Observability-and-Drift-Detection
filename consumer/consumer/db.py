from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
from pgvector.utils import Vector
from pgvector.psycopg import register_vector

# Must match the identical string used by every other component that runs
# migrations against this database (see detector/detector/db.py) --
# hashtext() derives the advisory lock key from it, and the lock only
# serializes correctly if every caller hashes the same string.
_MIGRATION_LOCK_KEY = "agentic_protection_schema_migrations"


class PgStore:
    def __init__(self, dsn: str):
        self.conn = psycopg.connect(dsn)


    def close(self) -> None:
        self.conn.close()

    def run_migrations(self, migrations_dir: Path, component: str) -> None:
        # A session-level advisory lock serializes migration application
        # across concurrent replicas -- without it, two instances starting
        # at once can both pass a bare `CREATE ... IF NOT EXISTS` check and
        # then race on the actual create, one throwing a duplicate-object
        # error. The schema_migrations ledger (keyed by component+filename,
        # since multiple components' migration directories share this
        # database) is what actually makes re-running this idempotent for
        # migrations that aren't themselves bare `IF NOT EXISTS` DDL --
        # without it, a future ALTER TABLE or backfill migration would
        # either error or double-apply on every restart.
        files = sorted(p for p in migrations_dir.glob("*.sql"))
        with self.conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(hashtext(%s)::bigint)", (_MIGRATION_LOCK_KEY,))
            self.conn.commit()
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
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s)::bigint)", (_MIGRATION_LOCK_KEY,))
                self.conn.commit()
        register_vector(self.conn)

    def insert_events(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return

        query = """
        INSERT INTO events_raw (
          kafka_topic, kafka_partition, kafka_offset, kafka_ts,
          request_id, route, session_id, frame_type, end_of_stream,
          headers, body, body_size, decision, blocked, warned,
          event_json, prompt_text, completion_text,
          prompt_embedding, completion_embedding, cohort
        ) VALUES (
          %(kafka_topic)s, %(kafka_partition)s, %(kafka_offset)s, %(kafka_ts)s,
          %(request_id)s, %(route)s, %(session_id)s, %(frame_type)s, %(end_of_stream)s,
          %(headers)s, %(body)s, %(body_size)s, %(decision)s, %(blocked)s, %(warned)s,
          %(event_json)s, %(prompt_text)s, %(completion_text)s,
          %(prompt_embedding)s, %(completion_embedding)s, %(cohort)s
        )
        ON CONFLICT (kafka_topic, kafka_partition, kafka_offset) DO NOTHING
        """

        prepared = []
        for row in rows:
            prepared.append(
                {
                    **row,
                    "headers": json.dumps(row.get("headers") or {}),
                    "event_json": json.dumps(row["event_json"]),
                    "prompt_embedding": Vector(row["prompt_embedding"]) if row.get("prompt_embedding") else None,
                    "completion_embedding": Vector(row["completion_embedding"]) if row.get("completion_embedding") else None,
                }
            )

        with self.conn.cursor() as cur:
            cur.executemany(query, prepared)
        self.conn.commit()
