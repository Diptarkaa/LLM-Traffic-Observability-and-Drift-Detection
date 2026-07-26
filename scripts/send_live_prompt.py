#!/usr/bin/env python3
"""Publish a single ad hoc prompt through the REAL capture pipeline, for
demoing the drift detector interactively -- type a prompt, watch it flow
through Kafka -> consumer -> detector -> dashboard exactly like real traffic.

Unlike scripts/check_prompt.py (which computes an instant verdict directly),
this actually exercises the whole system end-to-end, so there's a real delay:
a few seconds for the consumer to embed + store it, then up to
ONLINE_INTERVAL_SECONDS (default 30s) for the detector's next online-scoring
pass to pick it up.

    python3 scripts/send_live_prompt.py --text "..."
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib import request

BRIDGE_URL = "http://localhost:8082/events"


def _post(event: dict) -> None:
    payload = json.dumps(event).encode("utf-8")
    req = request.Request(BRIDGE_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    request.urlopen(req, timeout=5).read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a single live prompt through the real capture pipeline")
    parser.add_argument("--text", required=True, help="Prompt text")
    parser.add_argument("--response", default="Sure, here's the answer.", help="Canned completion text")
    parser.add_argument("--session-id", default=None, help="Session id (default: a fresh random one)")
    parser.add_argument("--route", default="/llm")
    args = parser.parse_args()

    session_id = args.session_id or f"live-demo-{uuid.uuid4().hex[:8]}"
    request_id = f"req-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    # Deliberately no "cohort" field -- real captured traffic never has one
    # (only the synthetic generator's output does, purely for grading). This
    # mirrors what genuine live traffic through extproc looks like.
    req_event = {
        "event_id": f"{request_id}-req",
        "source": "live-demo",
        "timestamp": now.isoformat(),
        "stream_id": request_id,
        "request_id": request_id,
        "session_id": session_id,
        "route": args.route,
        "frame_type": "request_body",
        "frame_seq": 1,
        "end_of_stream": True,
        "headers": {":path": args.route, "x-session-id": session_id},
        "body": args.text,
        "body_size": len(args.text.encode("utf-8")),
        "decision": "Safe",
        "blocked": False,
        "warned": False,
        "prompt": args.text,
        "completion": None,
    }
    res_event = {
        **req_event,
        "event_id": f"{request_id}-res",
        "timestamp": (now + timedelta(milliseconds=120)).isoformat(),
        "frame_type": "response_body",
        "frame_seq": 2,
        "headers": {"content-type": "text/plain", "x-session-id": session_id},
        "body": args.response,
        "body_size": len(args.response.encode("utf-8")),
        "prompt": None,
        "completion": args.response,
    }

    _post(req_event)
    _post(res_event)

    print(f"sent session_id={session_id!r}  request_id={request_id!r}  route={args.route!r}")
    print(f"prompt: {args.text!r}")
    print()
    print("Give it a few seconds to be embedded + stored, then up to ~30s for")
    print("the detector's next online-scoring pass. Check it via:")
    print(f"  - dashboard Session Drill-down page, session {session_id!r}")
    print(
        "  - docker compose exec postgres psql -U postgres -d agentic -c "
        f"\"select flagged_by, distance, threshold from drift_events where session_id='{session_id}';\""
    )


if __name__ == "__main__":
    main()
