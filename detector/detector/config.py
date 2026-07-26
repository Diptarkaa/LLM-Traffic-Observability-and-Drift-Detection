from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    postgres_dsn: str = os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@postgres:5432/agentic")

    # Fraction of each route's observed time range treated as "settled history"
    # for the nightly baseline job; the online job scores sessions with activity
    # after that cutoff. See migrations/001_drift_detection.sql for why.
    baseline_fraction: float = float(os.getenv("BASELINE_FRACTION", "0.5"))

    # Sessions scoring above (baseline mean distance + N * baseline std distance)
    # get flagged. The ticket's design doc suggests 3-sigma; empirically, on
    # this corpus, 3-sigma is calibrated to the baseline's own tight internal
    # spread (std ~1.6) and only ever catches noise (100% of noise sessions
    # cross it) -- drift sessions (worded as instruction-override attempts in
    # otherwise grammatical English) sit much closer to normal traffic in
    # embedding space than pure gibberish does, so they never reach a 3-sigma
    # bar. 2.0 was chosen by measuring actual precision/recall on the held-out
    # online-window data: ~41% drift recall against a ~5% normal false-positive
    # rate, vs. 3.0's 0% drift recall. See docs/week5-drift-dashboard.md.
    sigma_multiplier: float = float(os.getenv("DRIFT_SIGMA_MULTIPLIER", "2.0"))

    # Number of normal sub-clusters to fit per route (see migrations/
    # 002_multi_cluster_baseline.sql for why: a single centroid is a poor fit
    # when legitimate traffic has several distinct-but-legitimate topics).
    # Capped at fit-time by how many samples are actually available (see
    # _MIN_SAMPLES_PER_CLUSTER in baseline.py) -- this is just the ceiling.
    # Not yet empirically tuned the way sigma_multiplier was; a reasonable
    # starting point given ~2-3k baseline samples in this demo.
    n_clusters: int = int(os.getenv("DRIFT_N_CLUSTERS", "4"))

    # Cosine similarity above which a new message counts as "a repeat of a
    # previously confirmed drift example" (see migrations/
    # 003_known_drift_memory.sql). Checked globally, independent of route and
    # independent of the current baseline. Not yet empirically tuned the way
    # sigma_multiplier was -- verify against real paraphrase pairs before
    # trusting this default in a real deployment.
    known_drift_similarity_threshold: float = float(os.getenv("DRIFT_MEMORY_SIMILARITY_THRESHOLD", "0.9"))

    # Real cron expression for production ("0 2 * * *" = nightly at 2am).
    baseline_cron: str = os.getenv("BASELINE_CRON", "0 2 * * *")

    # How often the online scoring job re-runs. Short by default so a local
    # docker-compose demo shows results within a minute of data landing,
    # rather than requiring a wait for the nightly baseline_cron.
    online_interval_seconds: int = int(os.getenv("ONLINE_INTERVAL_SECONDS", "30"))

    # Run both jobs once immediately at process startup, in addition to their
    # schedules -- without this, a fresh `docker compose up` demo would show
    # nothing on the dashboard until the next scheduled firing.
    run_immediately_on_startup: bool = os.getenv("RUN_IMMEDIATELY_ON_STARTUP", "true").lower() == "true"
