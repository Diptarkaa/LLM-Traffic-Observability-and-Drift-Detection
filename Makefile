TEXT ?= how do i optimize sql indexes
K ?= 10
CLUSTERS ?= 8
LIMIT ?= 5000
CYCLES ?= 5000
SEED ?= 42

.PHONY: up down logs ps venv generate publish verify query-nearest query-clusters demo reset acceptance \
	detector-logs dashboard-logs drift-events drift-acceptance dashboard-demo open-dashboard \
	wait-ingestion wait-baseline

## Start the full stack: postgres, redpanda, kafka-bridge, consumer, detector, dashboard
up:
	docker compose up -d --build postgres redpanda kafka-bridge consumer detector dashboard

## Stop all services (keeps the postgres volume)
down:
	docker compose down

## Tail consumer logs
logs:
	docker compose logs -f consumer

## Tail detector logs (baseline + online scoring job output)
detector-logs:
	docker compose logs -f detector

## Tail dashboard logs
dashboard-logs:
	docker compose logs -f dashboard

ps:
	docker compose ps

## Create .venv with consumer's deps installed (needed to run scripts/query.py
## or scripts/validate.py against localhost instead of via `docker compose exec`)
venv:
	python3 -m venv .venv
	.venv/bin/pip install -e consumer

## Regenerate the synthetic 7-day dataset (stdlib only, no venv needed)
generate:
	python3 data/synth_generator.py --cycles $(CYCLES) --seed $(SEED) --out data/synth_events.jsonl

## Publish data/synth_events.jsonl into Kafka via the bridge (stdlib only, no venv needed)
publish:
	python3 scripts/publish_events.py --file data/synth_events.jsonl

## Row count in Postgres, to confirm no events were lost
verify:
	docker compose exec postgres psql -U postgres -d agentic -c "select count(*) from events_raw;"

## Nearest-neighbor query, run inside the consumer container (has all deps already)
## Usage: make query-nearest TEXT="ignore all previous instructions" K=10
query-nearest:
	docker compose exec consumer python scripts/query.py nearest-prompts --text "$(TEXT)" --k $(K)

## Cluster sizes with per-cluster cohort breakdown
## Usage: make query-clusters CLUSTERS=8 LIMIT=5000
query-clusters:
	docker compose exec consumer python scripts/query.py cluster-sizes --k $(CLUSTERS) --limit $(LIMIT)

## Poll events_raw until the row count stops changing (ingestion complete).
## A fixed sleep isn't reliable here -- embedding 10k events on CPU can take
## several minutes, and how long varies by machine, so this polls actual
## state instead of guessing a duration.
wait-ingestion:
	@echo "waiting for ingestion to settle (can take several minutes on CPU)..."
	@prev=-1; stable=0; \
	while [ $$stable -lt 3 ]; do \
		count=$$(docker compose exec -T postgres psql -U postgres -d agentic -t -c "select count(*) from events_raw;" 2>/dev/null | tr -d ' '); \
		count=$${count:-0}; \
		if [ "$$count" = "$$prev" ] && [ "$$count" -gt 0 ]; then stable=$$((stable+1)); else stable=0; fi; \
		prev=$$count; \
		sleep 5; \
	done; \
	echo "ingestion settled at $$prev rows"

## Poll detector logs until the first baseline computation completes, AND
## until the online-scoring job has run at least once AFTER that -- the
## online job runs on its own schedule (ONLINE_INTERVAL_SECONDS, default
## 30s) and can fire moments before the baseline finishes, so "a baseline
## exists" alone doesn't guarantee anything has actually been scored against
## it yet (observed live: a `drift-acceptance` run right after "baseline
## updated" appeared still showed 0 flagged sessions).
wait-baseline:
	@echo "waiting for the detector's first baseline pass..."
	@until docker compose logs detector --no-log-prefix 2>/dev/null | grep -q "baseline updated"; do sleep 5; done
	@echo "baseline established, waiting for the next online-scoring pass..."
	@before=$$(docker compose logs detector --no-log-prefix 2>/dev/null | grep -c "running online scoring job"); \
	after=$$before; \
	while [ "$$after" -le "$$before" ]; do \
		sleep 5; \
		after=$$(docker compose logs detector --no-log-prefix 2>/dev/null | grep -c "running online scoring job"); \
	done
	@echo "online scoring has run against the current baseline"

## Full run: start services, generate + publish data, verify ingestion, run both queries
demo: up generate publish wait-ingestion
	$(MAKE) verify
	$(MAKE) query-nearest
	$(MAKE) query-clusters

## Automated pass/fail check for all 4 Week 4 acceptance criteria (ingestion loss,
## nearest-neighbor sanity, dataset cohorts, drift detectability via similarity search)
acceptance:
	docker compose exec consumer python scripts/validate.py

## Row count in drift_events, to eyeball what the detector has flagged so far
drift-events:
	docker compose exec postgres psql -U postgres -d agentic -c \
		"select session_id, cohort, distance, threshold, turn_count, worst_event_ts from drift_events order by distance desc limit 20;"

## Automated pass/fail check for the Week 5 drift-detector acceptance criteria
## (baseline exists, at least one session flagged, at least one true positive)
drift-acceptance:
	docker compose exec detector python scripts/validate_drift.py

## Open the Streamlit dashboard in your browser (macOS)
open-dashboard:
	open http://localhost:8501 2>/dev/null || echo "Visit http://localhost:8501"

## Full Week 5 run: start the stack, load the synthetic dataset, wait for the
## detector's first pass, then check + open the dashboard
dashboard-demo: up generate publish wait-ingestion wait-baseline
	$(MAKE) drift-acceptance
	$(MAKE) open-dashboard

## Danger: drops the postgres volume, wiping all ingested data
reset:
	docker compose down -v
