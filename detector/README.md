# Detector

Cron-style drift detector. Runs two jobs against the same Postgres/pgvector
database the `consumer` writes to:

- **Baseline job** (`detector.baseline`) — per route, computes a centroid and
  per-dimension variance from the earliest `BASELINE_FRACTION` of that
  route's observed time range ("settled history"), plus a 3-sigma-style
  threshold derived from how spread out that baseline sample is around its
  own centroid.
- **Online job** (`detector.online`) — scores sessions with activity after
  the baseline window against that baseline, using diagonal Mahalanobis
  distance (see `distance.py` for why not full Mahalanobis). A session is
  flagged if its *worst* turn (not average -- see `online.py`) exceeds the
  threshold, and written to `drift_events`.

Both jobs run once immediately on startup (so a fresh demo shows results
without waiting for the schedule), then on their configured cadence:
`BASELINE_CRON` (real cron expression, default nightly at 2am) and
`ONLINE_INTERVAL_SECONDS` (default 30s, tuned for demo responsiveness).

## Environment variables

- `POSTGRES_DSN`
- `BASELINE_FRACTION` (default `0.5`)
- `DRIFT_SIGMA_MULTIPLIER` (default `2.0` -- see config.py for why this isn't the design doc's literal 3.0)
- `BASELINE_CRON` (default `0 2 * * *`)
- `ONLINE_INTERVAL_SECONDS` (default `30`)
- `RUN_IMMEDIATELY_ON_STARTUP` (default `true`)

## Run locally

```bash
cd detector
pip install .
detector-run
```
