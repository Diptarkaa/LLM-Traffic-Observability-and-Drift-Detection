# Kafka Integration (Python Bridge, Minimal Changes)

## What Changed
- Added a local Redpanda + kafka-bridge stack in docker-compose.
- Added a Python kafka-bridge service at sidecar/kafka-bridge.
- Added minimal linkage in grpc-inspection-server so every ext_proc frame is emitted asynchronously to bridge-url.

## Why This Design
- Keeps existing project topology intact.
- Avoids direct Kafka client dependency in extproc server.
- Fail-open by design: capture enqueue/drop and bridge failures never block Envoy responses.

## Local Bring-up
1. Start Kafka stack:

docker compose up -d --build redpanda kafka-bridge

2. Check bridge health:

curl -s http://localhost:8082/healthz

3. Verify Kafka receives a hand-crafted event:

curl -s -X POST http://localhost:8082/events \
  -H 'content-type: application/json' \
  -d '{"request_id":"manual-1","path":"/test","decision":"Safe"}'

docker compose exec redpanda rpk topic consume envoy.capture.events -n 1

## gRPC Server Capture Flags
- bridge-enabled (default true)
- bridge-url (default http://localhost:8082/events)
- bridge-queue-size (default 4096)
- bridge-timeout-ms (default 500)
- capture-sample-rate (default 1.0)

## Event Shape
One event per ext_proc frame (request_headers, request_body, response_headers, response_body) with:
- stream id and optional request id
- frame type and frame sequence
- frame headers (for header frames)
- frame body bytes as string and size (for body frames)
- end_of_stream flag
- inspection decision at that frame (safe/warn/block)

## Failure Mode Expectations
- Bridge down: extproc continues (events may be dropped by the bridge emitter on HTTP errors; current implementation does not log per-event failures by default), traffic continues.
- Bridge queue full: event dropped, traffic continues.
- Kafka down: bridge logs forwarding errors, extproc unaffected.
