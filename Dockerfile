FROM --platform=$BUILDPLATFORM golang:1.26-alpine AS builder
WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY main.go ./

ARG TARGETOS
ARG TARGETARCH

RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -o grpc-inspection main.go

FROM alpine:latest
WORKDIR /root/

COPY --from=builder /app/grpc-inspection .

EXPOSE 9000

CMD ["./grpc-inspection"]
