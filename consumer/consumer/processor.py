from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _header_value(headers: dict[str, Any], key: str) -> str | None:
    if not headers:
        return None
    for k, v in headers.items():
        if k.lower() == key.lower():
            return str(v)
    return None


def parse_event(msg_value: dict[str, Any], kafka_topic: str, partition: int, offset: int, timestamp_ms: int) -> dict[str, Any]:
    headers = msg_value.get("headers") or {}
    body = msg_value.get("body") or ""
    frame_type = msg_value.get("frame_type") or "unknown"

    route = (
        msg_value.get("route")
        or _header_value(headers, ":path")
        or _header_value(headers, "x-envoy-original-path")
    )
    session_id = msg_value.get("session_id") or _header_value(headers, "x-session-id")
    request_id = msg_value.get("request_id")

    prompt_text = None
    completion_text = None

    # For raw ext_proc frames, keep prompt/completion split by frame type.
    if frame_type == "request_body":
        prompt_text = body
    elif frame_type == "response_body":
        completion_text = body

    # Synthetic generator may publish cycle-level fields.
    if msg_value.get("prompt"):
        prompt_text = msg_value.get("prompt")
    if msg_value.get("completion"):
        completion_text = msg_value.get("completion")

    kafka_ts = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

    return {
        "kafka_topic": kafka_topic,
        "kafka_partition": partition,
        "kafka_offset": offset,
        "kafka_ts": kafka_ts,
        "request_id": request_id,
        "route": route,
        "session_id": session_id,
        "frame_type": frame_type,
        "end_of_stream": bool(msg_value.get("end_of_stream", False)),
        "headers": headers,
        "body": body,
        "body_size": int(msg_value.get("body_size", len(body.encode("utf-8")))),
        "decision": msg_value.get("decision", "Unknown"),
        "blocked": bool(msg_value.get("blocked", False)),
        "warned": bool(msg_value.get("warned", False)),
        "event_json": msg_value,
        "prompt_text": prompt_text,
        "completion_text": completion_text,
        "prompt_embedding": None,
        "completion_embedding": None,
        "cohort": msg_value.get("cohort"),
    }


def attach_embeddings(rows: list[dict[str, Any]], prompt_vectors: list[list[float]], completion_vectors: list[list[float]]) -> None:
    p_idx = 0
    c_idx = 0

    for row in rows:
        if row.get("prompt_text"):
            row["prompt_embedding"] = prompt_vectors[p_idx]
            p_idx += 1
        if row.get("completion_text"):
            row["completion_embedding"] = completion_vectors[c_idx]
            c_idx += 1
