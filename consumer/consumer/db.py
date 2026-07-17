from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
from pgvector.utils import Vector
from pgvector.psycopg import register_vector


class PgStore:
    def __init__(self, dsn: str):
        self.conn = psycopg.connect(dsn)
        

    def close(self) -> None:
        self.conn.close()

    def run_migrations(self, migrations_dir: Path) -> None:
        files = sorted(p for p in migrations_dir.glob("*.sql"))
        with self.conn.cursor() as cur:
            for path in files:
                cur.execute(path.read_text())
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
