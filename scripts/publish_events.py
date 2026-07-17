#!/usr/bin/env python3
"""Publish a synth_generator.py JSONL file to the kafka-bridge HTTP endpoint."""
from __future__ import annotations

import argparse
from pathlib import Path
from urllib import request


def publish(path: Path, url: str) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            req = request.Request(
                url,
                data=line.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            request.urlopen(req, timeout=5).read()
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish synthetic events to the kafka-bridge")
    parser.add_argument("--file", type=Path, default=Path("data/synth_events.jsonl"), help="JSONL file to publish")
    parser.add_argument("--url", default="http://localhost:8082/events", help="kafka-bridge /events endpoint")
    args = parser.parse_args()

    count = publish(args.file, args.url)
    print(f"published {count} events from {args.file} to {args.url}")


if __name__ == "__main__":
    main()
