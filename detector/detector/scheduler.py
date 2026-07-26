from __future__ import annotations

import logging
import os
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .baseline import compute_baselines
from .config import Settings
from .db import DriftStore
from .online import score_sessions

log = logging.getLogger("detector.scheduler")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = Settings()
    store = DriftStore(cfg.postgres_dsn)
    # Path(__file__).parents[1] only points at the project root when running
    # from a source checkout; once pip-installed into site-packages it
    # resolves to the wrong place, so MIGRATIONS_DIR must win when set (the
    # Dockerfile sets it to /app/migrations).
    default_migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    migrations_dir = Path(os.environ.get("MIGRATIONS_DIR", default_migrations_dir))
    store.run_migrations(migrations_dir, component="detector")

    def run_baseline() -> int:
        log.info("running baseline job")
        try:
            return compute_baselines(store, cfg)
        except Exception:
            log.exception("baseline job failed")
            return 0

    def run_online() -> None:
        log.info("running online scoring job")
        try:
            score_sessions(store, cfg)
        except Exception:
            log.exception("online scoring job failed")

    scheduler = BlockingScheduler()
    last_seen_counts: dict[str, int] = {}
    baseline_established = False

    def try_establish_baseline() -> None:
        # Cold-start case: the consumer may still be ingesting (or hasn't
        # started) when this container comes up, so the very first attempt
        # can legitimately find zero embeddings. Keep retrying on the same
        # short cadence as online scoring until a baseline exists, then
        # stop -- without this, a fresh `docker compose up` demo would show
        # nothing until the *next* nightly cron firing.
        #
        # Also wait for each route's embedding count to stop growing between
        # two consecutive checks before computing -- otherwise a baseline
        # computed mid-ingestion locks in a narrow, incomplete slice of
        # history rather than the full backfill, and (per baseline_cron)
        # won't get a chance to correct itself until the next nightly run.
        # This also means the very first call always defers (nothing to
        # compare against yet), which is intentional.
        nonlocal baseline_established

        routes = store.distinct_routes()
        if not routes:
            log.info("no routes with embeddings yet")
            return

        settled = True
        for route in routes:
            count = store.total_embedding_count(route)
            if last_seen_counts.get(route) != count:
                settled = False
            last_seen_counts[route] = count

        if not settled:
            log.info("ingestion still in progress, waiting before computing baseline")
            return

        if run_baseline() > 0:
            baseline_established = True
            log.info("baseline established after ingestion settled, stopping cold-start retry")
            if scheduler.get_job("baseline_retry"):
                scheduler.remove_job("baseline_retry")

    if cfg.run_immediately_on_startup:
        try_establish_baseline()
        run_online()

    if not baseline_established:
        scheduler.add_job(
            try_establish_baseline,
            IntervalTrigger(seconds=cfg.online_interval_seconds),
            id="baseline_retry",
        )

    scheduler.add_job(run_baseline, CronTrigger.from_crontab(cfg.baseline_cron), id="baseline")
    scheduler.add_job(run_online, IntervalTrigger(seconds=cfg.online_interval_seconds), id="online")

    log.info(
        "scheduler started: baseline cron=%r, online every %ds",
        cfg.baseline_cron, cfg.online_interval_seconds,
    )
    scheduler.start()


if __name__ == "__main__":
    main()
