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
	"github.com/AkamaiAAPH/agentic-protection/internal/encoding"
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

func payloadTypeToFrameType(pType inspector.PayloadType) string {
	switch pType {
	case inspector.RequestHeader:
		return "request_headers"
	case inspector.RequestBody:
		return "request_body"
	case inspector.ResponseHeader:
		return "response_headers"
	case inspector.ResponseBody:
		return "response_body"
	default:
		return "unknown"
	}
}

func headersToMapAndString(headers []*corev3.HeaderValue) (map[string]string, string) {
	if len(headers) == 0 {
		return nil, ""
	}

	headersMap := make(map[string]string, len(headers))
	var headerStr strings.Builder

	for _, header := range headers {
		if header == nil {
			continue
		}

		val := string(header.RawValue)
		if val == "" {
			val = header.Value
		}

		headersMap[header.Key] = val
		fmt.Fprintf(&headerStr, "%s: %s\n", header.Key, val)
	}

	return headersMap, strings.TrimSpace(headerStr.String())
}

func (s *ExtProcServer) emitCaptureEvent(state *streamCaptureState, payloadType inspector.PayloadType, headers map[string]string, body string, endOfStream bool, result inspector.Result) {
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
		FrameType:   payloadTypeToFrameType(payloadType),
		FrameSeq:    state.frameSeq.Add(1),
		EndOfStream: endOfStream,
		Headers:     headers,
		Body:        body,
		BodySize:    len([]byte(body)),
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
	var decompressor *encoding.Decompressor
	defer func() {
		if decompressor != nil {
			decompressor.Close()
		}
	}()

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
		var frameHeaders map[string]string

		switch payload := req.Request.(type) {
		case *extProcPb.ProcessingRequest_RequestHeaders:
			slog.Debug("Processing Request Headers")
			headersMap, headersStr := headersToMapAndString(payload.RequestHeaders.Headers.Headers)

			if strings.EqualFold(headerValue(headersMap, "pragma"), "akamai-x-get-service") {
				streamContext.ResponseHeaders["akamai-x-service"] = "agentic protection grpc inspection server"
			}

			payloadStr = headersStr
			payloadType = inspector.RequestHeader
			endOfStream = payload.RequestHeaders.EndOfStream
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
			slog.Debug("Request Body Content", "body", payloadStr)

		case *extProcPb.ProcessingRequest_ResponseHeaders:
			slog.Debug("Processing Response Headers")
			headersMap, headersStr := headersToMapAndString(payload.ResponseHeaders.Headers.Headers)
			streamContext.ContentEncoding = headerValue(headersMap, "content-encoding")

			decompressor = encoding.New(streamContext.ContentEncoding)

			payloadStr = headersStr
			payloadType = inspector.ResponseHeader
			endOfStream = payload.ResponseHeaders.EndOfStream
			frameHeaders = headersMap
			slog.Debug("Response Headers Content", "headers", payloadStr)

		case *extProcPb.ProcessingRequest_ResponseBody:
			slog.Debug("Processing Response Body")
			rawBytes := payload.ResponseBody.Body
			endOfStream = payload.ResponseBody.EndOfStream

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
			endOfStream = payload.ResponseBody.EndOfStream
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

		s.emitCaptureEvent(captureState, payloadType, frameHeaders, payloadStr, endOfStream, result)
	}
}
