from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from kafka import KafkaConsumer

from .config import Settings
from .db import PgStore
from .embedder import NomicEmbedder
from .processor import attach_embeddings, parse_event


def _build_consumer(cfg: Settings) -> KafkaConsumer:
    return KafkaConsumer(
        cfg.kafka_topic,
        bootstrap_servers=[x.strip() for x in cfg.kafka_bootstrap_servers.split(",") if x.strip()],
        group_id=cfg.kafka_group_id,
        enable_auto_commit=False,
        auto_offset_reset=cfg.auto_offset_reset,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        consumer_timeout_ms=0,
    )


def _flush_batch(batch: list[dict[str, Any]], store: PgStore, embedder: NomicEmbedder) -> None:
    if not batch:
        return

    prompts = [row["prompt_text"] for row in batch if row.get("prompt_text")]
    completions = [row["completion_text"] for row in batch if row.get("completion_text")]

    prompt_vectors = embedder.embed_prompts(prompts)
    completion_vectors = embedder.embed_completions(completions)
    attach_embeddings(batch, prompt_vectors, completion_vectors)

    store.insert_events(batch)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("consumer")

    cfg = Settings()
    log.info("starting consumer topic=%s group=%s", cfg.kafka_topic, cfg.kafka_group_id)

    store = PgStore(cfg.postgres_dsn)
    migrations_dir = Path(os.environ.get("MIGRATIONS_DIR", Path(__file__).resolve().parents[1] / "migrations"))
    store.run_migrations(migrations_dir)

    embedder = NomicEmbedder(cfg.embed_model_name, batch_size=cfg.embed_batch_size)
    consumer = _build_consumer(cfg)

    batch: list[dict[str, Any]] = []

    try:
        while True:
            records_pack = consumer.poll(timeout_ms=cfg.poll_timeout_ms)
            if not records_pack:
                if batch:
                    _flush_batch(batch, store, embedder)
                    consumer.commit()
                    log.info("committed batch size=%d", len(batch))
                    batch.clear()
                continue

            for tp, msgs in records_pack.items():
                for msg in msgs:
                    row = parse_event(
                        msg_value=msg.value,
                        kafka_topic=msg.topic,
                        partition=msg.partition,
                        offset=msg.offset,
                        timestamp_ms=msg.timestamp,
                    )
                    batch.append(row)

                    if len(batch) >= cfg.db_batch_size:
                        _flush_batch(batch, store, embedder)
                        consumer.commit()
                        log.info("committed batch size=%d", len(batch))
                        batch.clear()
    except KeyboardInterrupt:
        log.info("received interrupt, draining...")
        if batch:
            _flush_batch(batch, store, embedder)
            consumer.commit()
    finally:
        consumer.close()
        store.close()
        log.info("consumer stopped")


if __name__ == "__main__":
    main()
