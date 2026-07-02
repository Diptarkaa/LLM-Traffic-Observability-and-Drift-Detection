// Package main sets up and starts the gRPC server for Envoy's ext_proc filter.
package main

import (
	"flag"
	"fmt"
	"log/slog"
	"net"
	"os"
	"strings"

	"github.com/AkamaiAAPH/agentic-protection/internal/inspector"
	"github.com/AkamaiAAPH/agentic-protection/internal/server"

	extProcPb "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"google.golang.org/grpc"
)

func main() {
	// Parse command line arguments for the port and log level.
	portFlag := flag.String("port", "9000", "Port to run the gRPC server on")
	debugFlag := flag.Bool("debug", false, "Enable debug log level")
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

	// Create the ext_proc server implementation with inspector.
	extProcSrv := server.NewExtProcServer(keywordInspector)

	// Set up the gRPC server and register the ext_proc service.
	grpcServer := grpc.NewServer()
	extProcPb.RegisterExternalProcessorServer(grpcServer, extProcSrv)

	slog.Info("Starting ext_proc gRPC Server", "addr", addr)
	if err := grpcServer.Serve(lis); err != nil {
		slog.Error("Failed to serve", "err", err)
		os.Exit(1)
	}
}
