// Package server contains the implementation of the Envoy ext_proc gRPC service.
package server

import (
	"fmt"
	"io"
	"log"
	"strings"

	"github.com/AkamaiAAPH/agentic-protection/internal/inspector"

	extProcPb "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
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

		// Determine the type of payload.
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
				headerStr.WriteString(fmt.Sprintf("%s: %s\n", header.Key, val))
			}

			headersContent := strings.TrimSpace(headerStr.String())
			log.Printf("Request Headers Content:\n%s", headersContent)
			result := s.inspector.Inspect(inspector.RequestHeader, headersContent)

			switch result.Type {
			case inspector.Safe:
				log.Println("Verdict: Approved (Request Headers)")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_RequestHeaders{
						RequestHeaders: &extProcPb.HeadersResponse{},
					},
				}

			case inspector.Warn:
				log.Println("Verdict: Warn (Request Headers)")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_RequestHeaders{
						RequestHeaders: &extProcPb.HeadersResponse{},
					},
				}

			case inspector.Block:
				log.Println("Verdict: Blocked (Malicious Request Headers)")
				resp = buildBlockResponse(result.Body)
			}

		case *extProcPb.ProcessingRequest_RequestBody:
			log.Println("Processing Request Body")
			bodyStr := string(payload.RequestBody.Body)
			log.Printf("Request Body Content: %s", bodyStr)

			result := s.inspector.Inspect(inspector.RequestBody, bodyStr)

			switch result.Type {
			case inspector.Safe:
				log.Println("Verdict: Approved (Request Body)")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_RequestBody{
						RequestBody: &extProcPb.BodyResponse{},
					},
				}

			case inspector.Warn:
				log.Println("Verdict: Warn (Request Body)")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_RequestBody{
						RequestBody: &extProcPb.BodyResponse{},
					},
				}

			case inspector.Block:
				log.Println("Verdict: Blocked (Malicious Request Body)")
				resp = buildBlockResponse(result.Body)
			}

		case *extProcPb.ProcessingRequest_ResponseHeaders:
			log.Println("Processing Response Headers")
			var headerStr strings.Builder

			// Reconstruct headers into a single string for inspection.
			for _, header := range payload.ResponseHeaders.Headers.Headers {
				val := string(header.RawValue)
				if val == "" {
					val = header.Value
				}
				headerStr.WriteString(fmt.Sprintf("%s: %s\n", header.Key, val))
			}

			headersContent := strings.TrimSpace(headerStr.String())
			log.Printf("Response Headers Content:\n%s", headersContent)
			result := s.inspector.Inspect(inspector.ResponseHeader, headersContent)

			switch result.Type {
			case inspector.Safe:
				log.Println("Verdict: Approved (Response Headers)")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_ResponseHeaders{
						ResponseHeaders: &extProcPb.HeadersResponse{},
					},
				}

			case inspector.Warn:
				log.Println("Verdict: Warn (Response Headers)")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_ResponseHeaders{
						ResponseHeaders: &extProcPb.HeadersResponse{},
					},
				}

			case inspector.Block:
				log.Println("Verdict: Blocked (Malicious Response Headers)")
				resp = buildBlockResponse(result.Body)
			}

		case *extProcPb.ProcessingRequest_ResponseBody:
			log.Println("Processing Response Body")
			bodyStr := string(payload.ResponseBody.Body)
			log.Printf("Response Body Content: %s", bodyStr)

			result := s.inspector.Inspect(inspector.ResponseBody, bodyStr)

			switch result.Type {
			case inspector.Safe:
				log.Println("Verdict: Approved (Response Body)")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_ResponseBody{
						ResponseBody: &extProcPb.BodyResponse{},
					},
				}

			case inspector.Warn:
				log.Println("Verdict: Warn (Response Body)")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_ResponseBody{
						ResponseBody: &extProcPb.BodyResponse{},
					},
				}

			case inspector.Block:
				log.Println("Verdict: Blocked (Malicious Response Body)")
				resp = buildBlockResponse(result.Body)
			}

		default:
			// Fallback for unknown payload types.
			log.Printf("Unknown Payload Type: %T", payload)
			resp = &extProcPb.ProcessingResponse{
				Response: &extProcPb.ProcessingResponse_RequestHeaders{
					RequestHeaders: &extProcPb.HeadersResponse{},
				},
			}
		}

		// Send verdict back to Envoy.
		if err := stream.Send(resp); err != nil {
			log.Printf("Failed to send response back to Envoy: %v", err)
			return err
		}
	}
}

// buildBlockResponse creates a 403 Forbidden response to immediately stop the request.
func buildBlockResponse(message string) *extProcPb.ProcessingResponse {
	return &extProcPb.ProcessingResponse{
		Response: &extProcPb.ProcessingResponse_ImmediateResponse{
			ImmediateResponse: &extProcPb.ImmediateResponse{
				Status: &typev3.HttpStatus{
					Code: typev3.StatusCode_Forbidden,
				},
				Body: []byte(message),
			},
		},
	}
}
