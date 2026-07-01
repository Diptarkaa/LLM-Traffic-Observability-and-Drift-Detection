FROM --platform=$BUILDPLATFORM golang:1.26-alpine AS builder
WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY main.go ./
COPY internal ./internal/

ARG TARGETOS
ARG TARGETARCH

RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -o grpc-inspection main.go

FROM alpine:latest

RUN addgroup -g 10001 appgroup && \
    adduser -u 10001 -G appgroup -D -H appuser

USER 10001

WORKDIR /app

COPY --from=builder --chown=appuser:appgroup /app/grpc-inspection .

EXPOSE 9000

CMD ["./grpc-inspection"]
