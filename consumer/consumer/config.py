from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "envoy.capture.events")
    kafka_group_id: str = os.getenv("KAFKA_GROUP_ID", "agentic-consumer")
    postgres_dsn: str = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@postgres:5432/agentic")
    embed_model_name: str = os.getenv("EMBED_MODEL_NAME", "nomic-ai/nomic-embed-text-v1")
    embed_batch_size: int = int(os.getenv("EMBED_BATCH_SIZE", "32"))
    db_batch_size: int = int(os.getenv("DB_BATCH_SIZE", "256"))
    poll_timeout_ms: int = int(os.getenv("POLL_TIMEOUT_MS", "1000"))
    auto_offset_reset: str = os.getenv("AUTO_OFFSET_RESET", "earliest")
