// Package main sets up and starts the gRPC server for Envoy's ext_proc filter.
package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"math/rand"
	"net"
	"os"
	"strings"
	"time"

	"github.com/AkamaiAAPH/agentic-protection/internal/capture"
	"github.com/AkamaiAAPH/agentic-protection/internal/inspector"
	"github.com/AkamaiAAPH/agentic-protection/internal/server"

	extProcPb "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"google.golang.org/grpc"
)

func main() {
	rand.Seed(time.Now().UnixNano())

	// Parse command line arguments for the port and log level.
	portFlag := flag.String("port", "9000", "Port to run the gRPC server on")
	debugFlag := flag.Bool("debug", false, "Enable debug log level")
	bridgeEnabledFlag := flag.Bool("bridge-enabled", true, "Enable async capture emission to bridge service")
	bridgeURLFlag := flag.String("bridge-url", "http://localhost:8082/events", "HTTP endpoint for capture bridge")
	bridgeQueueSizeFlag := flag.Int("bridge-queue-size", 4096, "Async capture queue size")
	bridgeTimeoutMsFlag := flag.Int("bridge-timeout-ms", 500, "HTTP timeout in milliseconds for bridge calls")
	sampleRateFlag := flag.Float64("capture-sample-rate", 1.0, "Capture sample rate between 0.0 and 1.0")
	flag.Parse()

	logLevel := slog.LevelInfo
	if *debugFlag {
		logLevel = slog.LevelDebug
	}
	slog.SetDefault(slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: logLevel})))

	addr := fmt.Sprintf(":%s", strings.TrimPrefix(*portFlag, ":"))

	lis, err := net.Listen("tcp", addr)
	if err != nil {
		slog.Error("Failed to listen", "addr", addr, "err", err)
		os.Exit(1)
	}

	// Initialize the inspector.
	keywordInspector := inspector.NewKeywordInspector("malicious", "bypass")

	emitter := capture.NewNoopEmitter()
	if *bridgeEnabledFlag {
		bridgeEmitter, err := capture.NewHTTPBridgeEmitter(capture.HTTPBridgeConfig{
			EndpointURL: strings.TrimSpace(*bridgeURLFlag),
			QueueSize:   *bridgeQueueSizeFlag,
			Timeout:     time.Duration(*bridgeTimeoutMsFlag) * time.Millisecond,
		})
		if err != nil {
			slog.Warn("Bridge capture disabled due to init failure", "err", err)
		} else {
			emitter = bridgeEmitter
			slog.Info("Bridge capture enabled", "bridge_url", strings.TrimSpace(*bridgeURLFlag), "sample_rate", *sampleRateFlag)
		}
	} else {
		slog.Info("Bridge capture disabled")
	}
	defer func() {
		if err := emitter.Close(context.Background()); err != nil {
			slog.Warn("Failed to close capture emitter", "err", err)
		}
	}()

	// Create the ext_proc server implementation with inspector.
	extProcSrv := server.NewExtProcServer(keywordInspector, emitter, *sampleRateFlag)

	// Set up the gRPC server and register the ext_proc service.
	grpcServer := grpc.NewServer()
	extProcPb.RegisterExternalProcessorServer(grpcServer, extProcSrv)

	slog.Info("Starting ext_proc gRPC Server", "addr", addr)
	if err := grpcServer.Serve(lis); err != nil {
		slog.Error("Failed to serve", "err", err)
		os.Exit(1)
	}
}
