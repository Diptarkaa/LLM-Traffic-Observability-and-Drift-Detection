// Package server contains the implementation of the Envoy ext_proc gRPC service.
package server

import (
	"fmt"
	"io"
	"log/slog"
	"strings"

	"github.com/AkamaiAAPH/agentic-protection/internal/encoding"
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
	slog.Debug("New gRPC stream opened by Envoy")

	streamContext := &inspector.StreamContext{
		RequestHeaders:  make(map[string]string),
		ResponseHeaders: make(map[string]string),
	}
	var decompressor *encoding.Decompressor
	defer func() {
		if decompressor != nil {
			decompressor.Close()
		}
	}()

	// Continuously read messages from the stream until closed.
	for {
		req, err := stream.Recv()
		if err == io.EOF {
			slog.Debug("gRPC stream closed by Envoy")
			return nil
		}
		if err != nil {
			slog.Error("gRPC stream error", "err", err)
			return err
		}

		var resp *extProcPb.ProcessingResponse
		var payloadType inspector.PayloadType
		var payloadStr string

		switch payload := req.Request.(type) {
		case *extProcPb.ProcessingRequest_RequestHeaders:
			slog.Debug("Processing Request Headers")
			var headerStr strings.Builder

			// Reconstruct headers into a single string for inspection.
			for _, header := range payload.RequestHeaders.Headers.Headers {
				val := string(header.RawValue)
				if val == "" {
					val = header.Value
				}
				fmt.Fprintf(&headerStr, "%s: %s\n", header.Key, val)

				if strings.EqualFold(header.Key, "pragma") && strings.EqualFold(val, "akamai-x-get-service") {
					streamContext.ResponseHeaders["akamai-x-service"] = "agentic protection grpc inspection server"
				}
			}

			payloadStr = strings.TrimSpace(headerStr.String())
			payloadType = inspector.RequestHeader
			slog.Debug("Request Headers Content", "headers", payloadStr)

		case *extProcPb.ProcessingRequest_RequestBody:
			slog.Debug("Processing Request Body")
			payloadStr = string(payload.RequestBody.Body)
			payloadType = inspector.RequestBody
			slog.Debug("Request Body Content", "body", payloadStr)

		case *extProcPb.ProcessingRequest_ResponseHeaders:
			slog.Debug("Processing Response Headers")
			var headerStr strings.Builder

			// Reconstruct headers into a single string for inspection.
			for _, header := range payload.ResponseHeaders.Headers.Headers {
				val := string(header.RawValue)
				if val == "" {
					val = header.Value
				}
				fmt.Fprintf(&headerStr, "%s: %s\n", header.Key, val)

				if strings.EqualFold(header.Key, "content-encoding") {
					streamContext.ContentEncoding = val
				}
			}

			decompressor = encoding.New(streamContext.ContentEncoding)

			payloadStr = strings.TrimSpace(headerStr.String())
			payloadType = inspector.ResponseHeader
			slog.Debug("Response Headers Content", "headers", payloadStr)

		case *extProcPb.ProcessingRequest_ResponseBody:
			slog.Debug("Processing Response Body")
			rawBytes := payload.ResponseBody.Body
			endOfStream := payload.ResponseBody.EndOfStream

			if decompressor == nil {
				decompressor = encoding.New(streamContext.ContentEncoding)
			}

			decompressedBytes, err := decompressor.Decompress(rawBytes, endOfStream)
			if err != nil {
				slog.Error("Decompression error", "err", err)
				payloadStr = string(rawBytes)
			} else {
				payloadStr = string(decompressedBytes)
			}

			payloadType = inspector.ResponseBody
			slog.Debug("Response Body Content", "body", payloadStr)

		default:
			// Fallback for unknown payload types.
			slog.Warn("Unknown Payload Type", "type", fmt.Sprintf("%T", payload))
			return fmt.Errorf("unsupported ProcessingRequest type: %T", payload)
		}

		result := s.inspector.Inspect(payloadType, payloadStr, streamContext)
		slog.Info("verdict", "result", result)
		resp = buildResponse(payloadType, result, streamContext)

		// Send verdict back to Envoy.
		if err := stream.Send(resp); err != nil {
			slog.Error("Failed to send response back to Envoy", "err", err)
			return err
		}
	}
}
