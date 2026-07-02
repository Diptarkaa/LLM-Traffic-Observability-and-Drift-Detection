FROM --platform=$BUILDPLATFORM golang:1.26-alpine AS builder
WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY main.go ./

ARG TARGETOS
ARG TARGETARCH

RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -ldflags="-w -s" -o /app/h2cll main.go

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /

COPY --from=builder /app/h2cll /h2cll

USER nonroot:nonroot

EXPOSE 8000

ENTRYPOINT ["/h2cll"]
