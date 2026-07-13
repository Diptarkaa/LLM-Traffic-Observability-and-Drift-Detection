// Package server contains the implementation of the Envoy ext_proc gRPC service.
package server

import (
	"errors"
	"fmt"
	"io"
	"log/slog"
	"math/rand"
	"strings"
	"sync/atomic"
	"time"

	"github.com/AkamaiAAPH/agentic-protection/internal/capture"
	"github.com/AkamaiAAPH/agentic-protection/internal/inspector"

	corev3 "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extProcPb "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
)

// ExtProcServer handles the bidirectional stream with Envoy.
type ExtProcServer struct {
	extProcPb.UnimplementedExternalProcessorServer
	inspector  inspector.Inspector
	emitter    capture.Emitter
	sampleRate float64
	streamSeq  atomic.Uint64
}

// NewExtProcServer creates a new instance of ExtProcServer.
func NewExtProcServer(insp inspector.Inspector, emitter capture.Emitter, sampleRate float64) *ExtProcServer {
	if emitter == nil {
		emitter = capture.NewNoopEmitter()
	}
	if sampleRate < 0 {
		sampleRate = 0
	}
	if sampleRate > 1 {
		sampleRate = 1
	}

	return &ExtProcServer{
		inspector:  insp,
		emitter:    emitter,
		sampleRate: sampleRate,
	}
}

type streamCaptureState struct {
	enabled   bool
	streamID  string
	requestID string
	frameSeq  atomic.Uint64
}

func (s *ExtProcServer) shouldCapture() bool {
	if s.sampleRate <= 0 {
		return false
	}
	if s.sampleRate >= 1 {
		return true
	}
	return rand.Float64() < s.sampleRate
}

func headerValue(headers map[string]string, key string) string {
	for k, v := range headers {
		if strings.EqualFold(k, key) {
			return v
		}
	}
	return ""
}

func headersToMap(headers []*corev3.HeaderValue) map[string]string {
	if len(headers) == 0 {
		return nil
	}
	out := make(map[string]string, len(headers))
	for _, h := range headers {
		if h == nil {
			continue
		}
		val := string(h.RawValue)
		if val == "" {
			val = h.Value
		}
		out[h.Key] = val
	}
	return out
}

func (s *ExtProcServer) emitCaptureEvent(state *streamCaptureState, frameType string, headers map[string]string, body []byte, endOfStream bool, result inspector.Result) {
	if !state.enabled {
		return
	}

	now := time.Now().UTC()
	eventID := fmt.Sprintf("%d-%d", now.UnixNano(), s.streamSeq.Add(1))
	requestID := state.requestID
	if requestID == "" {
		requestID = state.streamID
	}

	event := capture.Event{
		EventID:     eventID,
		Source:      "grpc-extproc",
		Timestamp:   now,
		StreamID:    state.streamID,
		RequestID:   requestID,
		FrameType:   frameType,
		FrameSeq:    state.frameSeq.Add(1),
		EndOfStream: endOfStream,
		Headers:     headers,
		Body:        string(body),
		BodySize:    len(body),
		Decision:    result.String(),
		Blocked:     result == inspector.Block,
		Warned:      result == inspector.Warn,
	}

	if err := s.emitter.Emit(event); err != nil && !errors.Is(err, capture.ErrQueueFull) {
		slog.Warn("capture emit failed", "err", err)
	} else if errors.Is(err, capture.ErrQueueFull) {
		slog.Warn("capture emit dropped", "reason", "queue_full")
	}

}

// Process handles the gRPC stream.
// Envoy sends request/response body/header, and the server replies with actions (allow, block, modify).
func (s *ExtProcServer) Process(stream extProcPb.ExternalProcessor_ProcessServer) error {
	slog.Debug("New gRPC stream opened by Envoy")

	streamContext := &inspector.StreamContext{
		RequestHeaders:  make(map[string]string),
		ResponseHeaders: make(map[string]string),
	}

	streamID := fmt.Sprintf("stream-%d", s.streamSeq.Add(1))
	captureState := &streamCaptureState{
		enabled:  s.shouldCapture(),
		streamID: streamID,
	}

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
		var endOfStream bool
		var frameType string
		var frameHeaders map[string]string
		var frameBody []byte

		switch payload := req.Request.(type) {
		case *extProcPb.ProcessingRequest_RequestHeaders:
			slog.Debug("Processing Request Headers")
			var headerStr strings.Builder
			headersMap := headersToMap(payload.RequestHeaders.Headers.Headers)

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
			endOfStream = payload.RequestHeaders.EndOfStream
			frameType = "request_headers"
			frameHeaders = headersMap
			slog.Debug("Request Headers Content", "headers", payloadStr)

			if captureState.enabled {
				captureState.requestID = headerValue(headersMap, "x-request-id")
			}

		case *extProcPb.ProcessingRequest_RequestBody:
			slog.Debug("Processing Request Body")
			payloadStr = string(payload.RequestBody.Body)
			payloadType = inspector.RequestBody
			endOfStream = payload.RequestBody.EndOfStream
			frameType = "request_body"
			frameBody = payload.RequestBody.Body
			slog.Debug("Request Body Content", "body", payloadStr)

		case *extProcPb.ProcessingRequest_ResponseHeaders:
			slog.Debug("Processing Response Headers")
			var headerStr strings.Builder
			headersMap := headersToMap(payload.ResponseHeaders.Headers.Headers)

			// Reconstruct headers into a single string for inspection.
			for _, header := range payload.ResponseHeaders.Headers.Headers {
				if header == nil {
					continue
				}
				val := string(header.RawValue)
				if val == "" {
					val = header.Value
				}
				fmt.Fprintf(&headerStr, "%s: %s\n", header.Key, val)
			}

			payloadStr = strings.TrimSpace(headerStr.String())
			payloadType = inspector.ResponseHeader
			endOfStream = payload.ResponseHeaders.EndOfStream
			frameType = "response_headers"
			frameHeaders = headersMap
			slog.Debug("Response Headers Content", "headers", payloadStr)

		case *extProcPb.ProcessingRequest_ResponseBody:
			slog.Debug("Processing Response Body")
			payloadStr = string(payload.ResponseBody.Body)
			payloadType = inspector.ResponseBody
			endOfStream = payload.ResponseBody.EndOfStream
			frameType = "response_body"
			frameBody = payload.ResponseBody.Body
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

		s.emitCaptureEvent(captureState, frameType, frameHeaders, frameBody, endOfStream, result)
	}
}