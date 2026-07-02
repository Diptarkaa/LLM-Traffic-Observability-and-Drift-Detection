// Package server contains the implementation of the Envoy ext_proc gRPC service.
package server

import (
	"fmt"
	"io"
	"log"
	"strings"

	"github.com/AkamaiAAPH/agentic-protection/internal/inspector"

	extProcPb "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
)

// ExtProcServer handles the bidirectional stream with Envoy.
type ExtProcServer struct {
	extProcPb.UnimplementedExternalProcessorServer
	inspector inspector.Inspector
}

// NewExtProcServer creates a new instance of ExtProcServer.
func NewExtProcServer(insp inspector.Inspector) *ExtProcServer {
	return &ExtProcServer{inspector: insp}
}

// Process handles the gRPC stream.
// Envoy sends request/response body/header, and the server replies with actions (allow, block, modify).
func (s *ExtProcServer) Process(stream extProcPb.ExternalProcessor_ProcessServer) error {
	log.Println("New gRPC stream opened by Envoy")

	streamContext := &inspector.StreamContext{
		RequestHeaders:  make(map[string]string),
		ResponseHeaders: make(map[string]string),
	}

	// Continuously read messages from the stream until closed.
	for {
		req, err := stream.Recv()
		if err == io.EOF {
			log.Println("gRPC stream closed by Envoy")
			return nil
		}
		if err != nil {
			log.Printf("gRPC stream error: %v", err)
			return err
		}

		var resp *extProcPb.ProcessingResponse
		var payloadType inspector.PayloadType
		var payloadStr string

		switch payload := req.Request.(type) {
		case *extProcPb.ProcessingRequest_RequestHeaders:
			log.Println("Processing Request Headers")
			var headerStr strings.Builder

			// Reconstruct headers into a single string for inspection.
			for _, header := range payload.RequestHeaders.Headers.Headers {
				val := string(header.RawValue)
				if val == "" {
					val = header.Value
				}
				fmt.Fprintf(&headerStr, "%s: %s\n", header.Key, val)
			}

			payloadStr = strings.TrimSpace(headerStr.String())
			payloadType = inspector.RequestHeader
			log.Printf("Request Headers Content:\n%s", payloadStr)

		case *extProcPb.ProcessingRequest_RequestBody:
			log.Println("Processing Request Body")
			payloadStr = string(payload.RequestBody.Body)
			payloadType = inspector.RequestBody
			log.Printf("Request Body Content: %s", payloadStr)

		case *extProcPb.ProcessingRequest_ResponseHeaders:
			log.Println("Processing Response Headers")
			var headerStr strings.Builder

			// Reconstruct headers into a single string for inspection.
			for _, header := range payload.ResponseHeaders.Headers.Headers {
				val := string(header.RawValue)
				if val == "" {
					val = header.Value
				}
				fmt.Fprintf(&headerStr, "%s: %s\n", header.Key, val)
			}

			payloadStr = strings.TrimSpace(headerStr.String())
			payloadType = inspector.ResponseHeader
			log.Printf("Response Headers Content:\n%s", payloadStr)

		case *extProcPb.ProcessingRequest_ResponseBody:
			log.Println("Processing Response Body")
			payloadStr = string(payload.ResponseBody.Body)
			payloadType = inspector.ResponseBody
			log.Printf("Response Body Content: %s", payloadStr)

		default:
			// Fallback for unknown payload types.
			log.Printf("Unknown Payload Type: %T", payload)
			resp = &extProcPb.ProcessingResponse{
				Response: &extProcPb.ProcessingResponse_RequestHeaders{
					RequestHeaders: &extProcPb.HeadersResponse{},
				},
			}
		}

		if resp == nil {
			result := s.inspector.Inspect(payloadType, payloadStr, streamContext)
			log.Printf("verdict: %v", result)
			resp = buildResponse(payloadType, result, streamContext)
		}

		// Send verdict back to Envoy.
		if err := stream.Send(resp); err != nil {
			log.Printf("Failed to send response back to Envoy: %v", err)
			return err
		}
	}
}
