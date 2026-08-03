# Handoff: Status, Known Limitations, Next Steps

Snapshot as of the `feat/week5-drift-detector-dashboard` branch. This page consolidates limitations that are otherwise scattered across `docs/week5-drift-dashboard.md`, `docs/pr-checklist.md`, and `docs/perf.md`, plus branch/merge state that isn't written down anywhere else.

## Current state

- **Nothing is merged to `main` yet.** `main` is the initial commit only; all functionality (gateway inspection, Kafka capture, embeddings pipeline, drift detector, dashboard, Helm chart) lives on feature branches. This branch is 44 commits ahead of `main`.
- **Two independent halves, connected one-way.** The inline gateway/inspection path (Go `ext_proc` + Envoy Gateway + Helm) and the offline analytics pipeline (Kafka capture → consumer → detector → dashboard, via `docker compose`) only talk to each other in one direction: gateway → Kafka. Drift detection does not feed back into the gateway's live block/allow decision.
- **The gateway's real content inspector is on a separate, unmerged branch.** What's running on this branch is a placeholder `KeywordInspector` (blocks on the literal string "malicious", warns on "bypass"). A more capable Python inspector built on the open-source `llm-guard` library (prompt-injection detection, PII/secrets scanning, malicious-URL detection) exists on `origin/feat/ORGWAAP-7422-llm-guard`, but that branch forked before the Kafka/embeddings/detector work existed and has never been reconciled with it — merging the two means deciding whether Go or Python is the inspector going forward, and porting the async fail-open Kafka-capture hook if Python is chosen.
- **A Kubernetes cluster context exists (`lke557035-ctx`, namespace `llmg`) but the gateway stack isn't deployed there** — only a stray `frontend-app` pod is running. Envoy Gateway and the Gateway API CRDs aren't installed on it.

## Known limitations

Ordered roughly by how much they'd change a stated result if someone pushed on it.

1. **The drift detector's baseline fit is not run-to-run reproducible.** `detector/detector/baseline.py` fits `MiniBatchKMeans` with a fixed `random_state=42`, but `db.py`'s `fetch_embeddings` has no `ORDER BY`, and `MiniBatchKMeans` draws sequential mini-batches from whatever order the input arrives in — so the fixed seed does not make the fit deterministic. Re-fitting the identical `n_clusters=4` config against the identical baseline window, varying only input row order, swung drift recall from 43/80 (54%) to 77/80 (96%) and normal-cohort false positives from 10/300 to 36/300. This was also observed live in this deployment: a scheduled baseline refit moved measured normal false positives from 19/300 to 72/300 on unchanged data. **This means the "80/80 (100%) recall" headline number in `docs/week5-drift-dashboard.md` is one favorable sample from a noisy process, not a guaranteed result.** Full detail there under "Known limitations."
2. **`n_clusters` and `DRIFT_MEMORY_SIMILARITY_THRESHOLD` were never empirically swept**, unlike `DRIFT_SIGMA_MULTIPLIER` (which was tuned 3.0 → 2.0 against measured recall/false-positive data). A sweep isn't meaningful until (1) is fixed first — right now it would be measuring clustering luck, not the parameter.
3. **Only one route (`/llm`) exists in the synthetic corpus.** The baseline/scoring logic is written to be route-generic (`distinct_routes()` drives everything), but multi-route behavior has never actually been exercised.
4. **Normal-cohort false positives are inherent, and the rate is wider than originally documented.** Instruction-override phrasing sits close to ordinary English in embedding space; combined with (1), observed false-positive rates on identical data have ranged from ~6% to ~24%.
5. **The cold-start baseline trigger won't work in real production.** `detector/detector/scheduler.py` retries baseline computation until each route's embedding count stops changing between checks — a reasonable proxy for "ingestion has caught up" in a one-shot demo replay, but a continuously-streaming production deployment never "settles" in that sense. A real deployment needs a different trigger (e.g. a fixed startup grace period).
6. **The perf-overhead benchmark was never executed.** `docs/perf.md` documents a test plan (p50/p95/p99 latency with capture on vs. off, at 100 RPS for 5 minutes, acceptance bar of <20ms p99 delta) with a results table still marked `TBD`, and `docs/pr-checklist.md` has the corresponding checkbox unchecked. Running it requires the gateway stack actually deployed to a cluster (see "Current state" above) — not something available from a local dev machine.
7. **Detection-only, no enforcement loop.** Even a correctly-tuned drift detector only ever writes to a dashboard today. Whether/how a confirmed-drift signal should affect the live gateway decision (e.g. auto-adding to a block list, feeding `known_drift_embeddings` back into the inspector) is an open design question, not started.

## Next steps

Roughly in priority order:

1. **Fix baseline reproducibility.** Swap `MiniBatchKMeans` → full-batch `KMeans` with multiple restarts in `detector/detector/baseline.py` (the baseline fit is ~2,500 points, run once a night — not a scale or latency problem, so there's no reason to keep the mini-batch/stochastic version). Add an explicit `ORDER BY` to `fetch_embeddings` regardless, as defense in depth.
2. **Re-run the `n_clusters` / memory-threshold sweep** once (1) is done, and update the defaults + `docs/week5-drift-dashboard.md` with results that will actually hold up on re-measurement.
3. **Reconcile the `llm-guard` branch** with this branch: decide Go vs. Python for the inspector, and if Python, port over the fail-open async Kafka-capture path (`capture/emitter.go` equivalent) so the two halves stay connected.
4. **Actually run the perf benchmark** once the gateway stack is deployed to a real cluster — fill in `docs/perf.md`'s results table and check the corresponding `docs/pr-checklist.md` box.
5. **Extend the synthetic generator to multiple routes** to validate that per-route baselines behave correctly when more than one route exists.
6. **Design a real production cold-start trigger** (e.g. a fixed `BASELINE_STARTUP_GRACE_SECONDS`) to replace the ingestion-stabilization heuristic before this runs against genuinely continuous traffic.
7. **Decide on an enforcement story**: should a confirmed drift session (or a `known_drift_embeddings` match) ever feed back into the gateway's live block/allow decision, and if so, how.
8. **Get this branch (and the reconciled llm-guard work) merged to `main`** — currently blocked on stakeholder approval, not a technical blocker.
