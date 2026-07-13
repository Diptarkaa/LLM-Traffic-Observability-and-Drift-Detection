# Performance Notes

## Goal
Measure incremental latency with capture enabled vs disabled at 100 RPS for 5 minutes.

## Test Shape
- Traffic path: Envoy Gateway -> ext_proc gRPC server -> backend app
- Capture path: ext_proc -> async POST to kafka-bridge -> Redpanda
- Mode: fail open (capture errors are dropped)

## Configuration
- capture sample rate: 1.0
- capture body cap: none (currently emits full ext_proc frame bodies)
- bridge timeout: 500ms
- bridge queue size: 4096

## Command Template
Use your preferred load generator. Example with wrk:

wrk -t4 -c64 -d5m -R100 https://<gateway-host>/sse/safe

Run twice:
1. bridge disabled in grpc inspection server
2. bridge enabled

## Report Template
Fill this table after your run:

| Run | p50 (ms) | p95 (ms) | p99 (ms) | Notes |
| --- | --- | --- | --- | --- |
| Capture disabled | TBD | TBD | TBD | baseline |
| Capture enabled | TBD | TBD | TBD | async bridge on |

## Acceptance Check
- p99 delta should stay below 20ms.
- If above 20ms, reduce sample rate and re-measure.
