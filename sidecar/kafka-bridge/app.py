import json
import logging
import os
import queue
import threading
from typing import Any, Dict

from fastapi import FastAPI
from kafka import KafkaProducer

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("kafka-bridge")

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "envoy.capture.events")
QUEUE_SIZE = int(os.getenv("EVENT_QUEUE_SIZE", "10000"))

_event_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=QUEUE_SIZE)
_stop_event = threading.Event()


def _producer_loop() -> None:
    producer = KafkaProducer(
        bootstrap_servers=[s.strip() for s in BOOTSTRAP_SERVERS.split(",") if s.strip()],
        acks=1,
        linger_ms=10,
        retries=0,
        value_serializer=lambda v: v,
    )

    logger.info("Kafka producer started", extra={"topic": TOPIC, "brokers": BOOTSTRAP_SERVERS})

    while not _stop_event.is_set():
        try:
            item = _event_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            producer.send(TOPIC, item)
        except Exception:
            logger.exception("Failed to forward event to Kafka")
        finally:
            _event_queue.task_done()

    try:
        producer.flush(timeout=5)
        producer.close(timeout=5)
    except Exception:
        logger.exception("Failed to flush Kafka producer during shutdown")


app = FastAPI(title="kafka-bridge", version="1.0.0")
_worker = threading.Thread(target=_producer_loop, daemon=True)
_worker.start()


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    return {
        "ok": True,
        "topic": TOPIC,
        "brokers": BOOTSTRAP_SERVERS,
        "queue_depth": _event_queue.qsize(),
        "queue_capacity": QUEUE_SIZE,
    }


@app.post("/events")
def post_event(event: Dict[str, Any]) -> Dict[str, Any]:
    # Keep endpoint lenient so extproc can post a plain JSON envelope.
    payload = json.dumps(event, separators=(",", ":")).encode("utf-8")

    try:
        _event_queue.put_nowait(payload)
    except queue.Full:
        logger.warning("Bridge queue full, dropping event")
        return {"accepted": False, "dropped": True, "reason": "queue_full"}

    return {"accepted": True}
