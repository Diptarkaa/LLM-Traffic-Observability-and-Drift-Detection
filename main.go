// Package main sets up and starts the gRPC server for Envoy's ext_proc filter.
package main

import (
	"flag"
	"fmt"
	"log"
	"net"
	"strings"

	"grpc-inspection/internal/inspector"
	"grpc-inspection/internal/server"

	extProcPb "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	"google.golang.org/grpc"
)

func main() {
	// Parse command line arguments for the port.
	portFlag := flag.String("port", "9000", "Port to run the gRPC server on")
	flag.Parse()

	addr := fmt.Sprintf(":%s", strings.TrimPrefix(*portFlag, ":"))

	lis, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatalf("Failed to listen on %s: %v", addr, err)
	}

	// Initialize the inspector.
	keywordInspector := inspector.NewKeywordInspector("malicious")

	// Create the ext_proc server implementation with inspector.
	extProcSrv := server.NewExtProcServer(keywordInspector)

	// Set up the gRPC server and register the ext_proc service.
	grpcServer := grpc.NewServer()
	extProcPb.RegisterExternalProcessorServer(grpcServer, extProcSrv)

	log.Printf("Starting ext_proc gRPC Server on port %s", addr)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}
