#!/usr/bin/env python3
"""Automated pass/fail check for the Week 5 drift-detector acceptance criteria.

Run inside the detector container (has DB access + the drift_events/route_baselines
schema already):
    docker compose exec detector python scripts/validate_drift.py
"""
from __future__ import annotations

import os
import sys

import psycopg

DSN = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/agentic")

results: list[bool] = []


def check(name: str, passed: bool, detail: str) -> None:
    results.append(passed)
    print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")


def main() -> None:
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from route_baselines")
            baseline_count = cur.fetchone()[0]
            check(
                "baseline computed for at least one route",
                baseline_count > 0,
                f"{baseline_count} route(s) have a baseline (run `make up` and wait for the detector's first pass)",
            )

            cur.execute("select count(*) from drift_events")
            total_flagged = cur.fetchone()[0]
            check("at least one session flagged", total_flagged > 0, f"{total_flagged} session(s) flagged")

            cur.execute("select count(*) from drift_events where cohort = 'drift'")
            true_positive_count = cur.fetchone()[0]
            check(
                "at least one true-positive drift event (flagged AND cohort=drift)",
                true_positive_count > 0,
                f"{true_positive_count} flagged session(s) are genuinely from the synthetic drift cohort",
            )

            cur.execute("select cohort, count(*) from drift_events group by cohort order by 2 desc")
            breakdown = cur.fetchall()
            print(f"\nFlagged-session cohort breakdown: {dict(breakdown)}")

    print()
    all_passed = all(results)
    print("ALL CHECKS PASSED" if all_passed else "SOME CHECKS FAILED")
    print(
        "\nNote: this script covers the automatable criterion (a true-positive drift event\n"
        "exists). 'Dashboard runs from a fresh docker-compose up' and 'mentor can navigate\n"
        "without intern intervention' need a real `make reset && make up` + manual click-through."
    )
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
