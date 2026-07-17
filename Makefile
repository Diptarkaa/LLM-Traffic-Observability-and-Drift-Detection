TEXT ?= how do i optimize sql indexes
K ?= 10
CLUSTERS ?= 8
LIMIT ?= 5000
CYCLES ?= 5000
SEED ?= 42

.PHONY: up down logs ps venv generate publish verify query-nearest query-clusters demo reset acceptance

## Start postgres, redpanda, kafka-bridge and the consumer
up:
	docker compose up -d --build postgres redpanda kafka-bridge consumer

## Stop all services (keeps the postgres volume)
down:
	docker compose down

## Tail consumer logs
logs:
	docker compose logs -f consumer

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

## Full run: start services, generate + publish data, verify ingestion, run both queries
demo: up generate publish
	@echo "waiting for the consumer to catch up..."
	@sleep 20
	$(MAKE) verify
	$(MAKE) query-nearest
	$(MAKE) query-clusters

## Automated pass/fail check for all 4 acceptance criteria (ingestion loss,
## nearest-neighbor sanity, dataset cohorts, drift detectability)
acceptance:
	docker compose exec consumer python scripts/validate.py

## Danger: drops the postgres volume, wiping all ingested data
reset:
	docker compose down -v
