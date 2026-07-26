from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from .config import Settings
from .db import DriftStore
from .distance import nearest_cluster_distance

log = logging.getLogger("detector.online")


def score_sessions(store: DriftStore, cfg: Settings) -> None:
    routes = store.distinct_routes()
    flagged_total = 0

    for route in routes:
        baseline = store.fetch_baseline(route)
        if baseline is None:
            log.info("route=%s has no baseline yet, skipping online scoring", route)
            continue

        candidates = store.fetch_online_candidates(route, baseline["window_end"])
        if not candidates:
            continue

        sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in candidates:
            sessions[row["session_id"]].append(row)

        for session_id, turns in sessions.items():
            # Two independent signals per turn:
            #  (1) statistical -- is this far from every normal sub-cluster
            #      (baseline-distance, as before). Catches novel drift that
            #      doesn't resemble anything seen previously.
            #  (2) memory -- does this match a previously CONFIRMED drift
            #      example, regardless of route or the baseline's current
            #      shape (see db.py's nearest_known_drift_similarity). Catches
            #      repeats/paraphrases instantly, with no dependency on
            #      baseline recomputation.
            # Score every turn, keep the worst (max distance) one for the
            # statistical signal -- a drift session looks normal for most of
            # its turns by design and only pivots partway through, so
            # averaging would dilute the signal we're trying to catch.
            worst = None
            worst_distance = -1.0
            memory_hit = None
            memory_similarity = -1.0

            for turn in turns:
                d, _ = nearest_cluster_distance(turn["embedding"], baseline["clusters"])
                if d > worst_distance:
                    worst_distance = d
                    worst = turn

                is_baseline_hit = d > baseline["threshold"]

                similarity = store.nearest_known_drift_similarity(turn["embedding"])
                is_memory_hit = (
                    similarity is not None and similarity >= cfg.known_drift_similarity_threshold
                )
                if is_memory_hit and similarity > memory_similarity:
                    memory_similarity = similarity
                    memory_hit = turn

                # Any turn confirmed by either signal joins the permanent
                # memory -- so it (or a close paraphrase of it) gets caught
                # instantly next time, on any route, even before the next
                # baseline recompute.
                if is_baseline_hit or is_memory_hit:
                    store.remember_drift_embedding(
                        request_id=turn["request_id"],
                        session_id=session_id,
                        route=route,
                        prompt_text=turn["prompt_text"],
                        embedding=turn["embedding"],
                        distance=d,
                    )

            is_statistical_hit = worst is not None and worst_distance > baseline["threshold"]
            is_memory_flag = memory_hit is not None

            if is_statistical_hit or is_memory_flag:
                trigger_turn = worst if is_statistical_hit else memory_hit
                if is_statistical_hit and is_memory_flag:
                    flagged_by = "both"
                elif is_statistical_hit:
                    flagged_by = "baseline"
                else:
                    flagged_by = "memory"

                store.upsert_drift_event(
                    session_id=session_id,
                    route=route,
                    worst_request_id=trigger_turn["request_id"],
                    worst_event_ts=trigger_turn["event_ts"],
                    worst_prompt_text=trigger_turn["prompt_text"],
                    cohort=trigger_turn["cohort"],
                    distance=worst_distance,
                    threshold=baseline["threshold"],
                    turn_count=len(turns),
                    flagged_by=flagged_by,
                )
                flagged_total += 1

    if flagged_total:
        log.info("online scoring flagged %d session(s) this pass", flagged_total)
