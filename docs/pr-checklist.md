# PR Checklist: Kafka Capture Integration

Use this checklist directly in the PR description.

## Deliverables Mapped To Files

- [x] Redpanda (Kafka-compatible) added for local development
  - [docker-compose.yml](../docker-compose.yml)
  - [k8s-deployment/kafka/redpanda.yaml](../k8s-deployment/kafka/redpanda.yaml)

- [x] Kafka bridge sidecar implemented as Python service exposing POST /events
  - [sidecar/kafka-bridge/app.py](../sidecar/kafka-bridge/app.py)
  - [sidecar/kafka-bridge/requirements.txt](../sidecar/kafka-bridge/requirements.txt)
  - [sidecar/kafka-bridge/Dockerfile](../sidecar/kafka-bridge/Dockerfile)
  - [k8s-deployment/kafka/kafka-bridge.yaml](../k8s-deployment/kafka/kafka-bridge.yaml)

- [x] Raw ext_proc frame emission wired from ext_proc path (minimal linkage)
  - [grpc-inspection-server/internal/server/extproc.go](../grpc-inspection-server/internal/server/extproc.go)
  - [grpc-inspection-server/internal/capture/event.go](../grpc-inspection-server/internal/capture/event.go)
  - [grpc-inspection-server/internal/capture/emitter.go](../grpc-inspection-server/internal/capture/emitter.go)
  - [grpc-inspection-server/internal/capture/http_bridge.go](../grpc-inspection-server/internal/capture/http_bridge.go)
  - [grpc-inspection-server/main.go](../grpc-inspection-server/main.go)

- [x] Requests/responses forwarded as raw frames (no summary aggregation)
  - [grpc-inspection-server/internal/server/extproc.go](../grpc-inspection-server/internal/server/extproc.go)
  - [grpc-inspection-server/internal/capture/event.go](../grpc-inspection-server/internal/capture/event.go)

- [x] Sample-rate knob (default 1.0)
  - [grpc-inspection-server/main.go](../grpc-inspection-server/main.go) (flag: capture-sample-rate)
  - [grpc-inspection-server/internal/server/extproc.go](../grpc-inspection-server/internal/server/extproc.go) (shouldCapture)

- [x] Fail-open capture path (never block user traffic)
  - [grpc-inspection-server/internal/server/extproc.go](../grpc-inspection-server/internal/server/extproc.go) (emit errors logged/dropped)
  - [grpc-inspection-server/internal/capture/http_bridge.go](../grpc-inspection-server/internal/capture/http_bridge.go) (async queue + non-blocking emit)
  - [sidecar/kafka-bridge/app.py](../sidecar/kafka-bridge/app.py) (queue full and Kafka failures drop/log)

- [x] gRPC inspection deployment linked to bridge service
  - [k8s-deployment/grpc-inspection/grpc-inspection-server.yaml](../k8s-deployment/grpc-inspection/grpc-inspection-server.yaml)

- [x] End-to-end smoke test instructions (Envoy/extproc -> bridge -> Kafka)
  - [docs/kafka-integration.md](kafka-integration.md)

- [x] Performance test template and acceptance threshold documentation
  - [docs/perf.md](perf.md)

## Out-Of-Scope / Updated Design Notes

- [ ] Lua plugin deliverables are not implemented by design update (capture moved to ext_proc server + Python bridge).
  - Replacement implementation docs: [docs/kafka-integration.md](kafka-integration.md)

## Acceptance Criteria Traceability

- [x] ext_proc frames emit capture events as observed (best-effort, at-most-once per frame)
  - [grpc-inspection-server/internal/server/extproc.go](../grpc-inspection-server/internal/server/extproc.go)
  - [sidecar/kafka-bridge/app.py](../sidecar/kafka-bridge/app.py)

- [x] Bridge forwards payload as received (without adding metadata fields)
  - [sidecar/kafka-bridge/app.py](../sidecar/kafka-bridge/app.py)

- [x] Sidecar outage does not affect user traffic (fail-open path)
  - [grpc-inspection-server/internal/server/extproc.go](../grpc-inspection-server/internal/server/extproc.go)
  - [grpc-inspection-server/internal/capture/http_bridge.go](../grpc-inspection-server/internal/capture/http_bridge.go)

- [ ] p99 overhead < 20ms at 100 RPS (requires runtime benchmark execution)
  - Measurement template: [docs/perf.md](perf.md)
