// Package server contains the implementation of the Envoy ext_proc gRPC service.
package server

import (
	"fmt"
	"io"
	"log"
	"strings"

	"grpc-inspection/internal/inspector"

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
	log.Println("\nNew gRPC stream opened by Envoy")

	// Continuously read messages from the stream until closed.
	for {
		req, err := stream.Recv()
		if err == io.EOF {
			log.Println("\ngRPC stream closed by Envoy")
			return nil
		}
		if err != nil {
			log.Printf("gRPC stream error: %v\n", err)
			return err
		}

		var resp *extProcPb.ProcessingResponse

		// Determine the type of payload.
		switch payload := req.Request.(type) {

		case *extProcPb.ProcessingRequest_RequestHeaders:
			log.Println("\tRequest Headers")
			var headerStr strings.Builder

			// Reconstruct headers into a single string for inspection.
			for _, header := range payload.RequestHeaders.Headers.Headers {
				val := string(header.RawValue)
				if val == "" {
					val = header.Value
				}
				headerStr.WriteString(fmt.Sprintf("%s: %s\n", header.Key, val))
			}
			log.Println(headerStr.String())

			result := s.inspector.Inspect(inspector.RequestHeader, headerStr.String())

			if result.IsBlocked {
				log.Println("\t\tBlocked Malicious Request Headers")
				resp = buildBlockResponse(result.Message)
			} else {
				log.Println("\t\tApproved Request Headers")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_RequestHeaders{
						RequestHeaders: &extProcPb.HeadersResponse{},
					},
				}
			}

		case *extProcPb.ProcessingRequest_RequestBody:
			log.Println("\tRequest Body")
			bodyStr := string(payload.RequestBody.Body)
			log.Println(bodyStr)

			result := s.inspector.Inspect(inspector.RequestBody, bodyStr)

			if result.IsBlocked {
				log.Println("\t\tBlocked Malicious Request Body")
				resp = buildBlockResponse(result.Message)
			} else {
				log.Println("\t\tApproved Request Body")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_RequestBody{
						RequestBody: &extProcPb.BodyResponse{},
					},
				}
			}

		case *extProcPb.ProcessingRequest_ResponseHeaders:
			log.Println("\tResponse Headers")
			var headerStr strings.Builder

			// Reconstruct headers into a single string for inspection.
			for _, header := range payload.ResponseHeaders.Headers.Headers {
				val := string(header.RawValue)
				if val == "" {
					val = header.Value
				}
				headerStr.WriteString(fmt.Sprintf("%s: %s\n", header.Key, val))
			}
			log.Println(headerStr.String())

			result := s.inspector.Inspect(inspector.ResponseHeader, headerStr.String())

			if result.IsBlocked {
				log.Println("\t\tBlocked Malicious Response Headers")
				resp = buildBlockResponse(result.Message)
			} else {
				log.Println("\t\tApproved Response Headers")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_ResponseHeaders{
						ResponseHeaders: &extProcPb.HeadersResponse{},
					},
				}
			}

		case *extProcPb.ProcessingRequest_ResponseBody:
			log.Println("\tResponse Body")
			bodyStr := string(payload.ResponseBody.Body)
			log.Println(bodyStr)

			result := s.inspector.Inspect(inspector.ResponseBody, bodyStr)

			if result.IsBlocked {
				log.Println("\t\tBlocked Malicious Response Body")
				resp = buildBlockResponse(result.Message)
			} else {
				log.Println("\t\tApproved Response Body")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_ResponseBody{
						ResponseBody: &extProcPb.BodyResponse{},
					},
				}
			}

		default:
			// Fallback for unknown payload types.
			log.Printf("\tUnknown Payload Type: %T", payload)
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
