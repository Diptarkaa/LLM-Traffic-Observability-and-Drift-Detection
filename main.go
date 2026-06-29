package main

import (
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"strings"

	extProcPb "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
	"google.golang.org/grpc"
)

type extProcServer struct {
	extProcPb.UnimplementedExternalProcessorServer
}

func (s *extProcServer) Process(stream extProcPb.ExternalProcessor_ProcessServer) error {
	log.Println("\n\nNew gRPC stream opened by Envoy")

	for {
		req, err := stream.Recv()
		if err == io.EOF {
			log.Println("\ngRPC stream closed by Envoy\n")
			return nil
		}
		if err != nil {
			log.Printf("gRPC stream error: %v\n", err)
			return err
		}

		var resp *extProcPb.ProcessingResponse

		switch payload := req.Request.(type) {

		case *extProcPb.ProcessingRequest_RequestHeaders:
			log.Println("\tRequest Headers")

			resp = &extProcPb.ProcessingResponse{
				Response: &extProcPb.ProcessingResponse_RequestHeaders{
					RequestHeaders: &extProcPb.HeadersResponse{},
				},
			}

			for _, header := range payload.RequestHeaders.Headers.Headers {
				val := string(header.RawValue)
				if val == "" {
					val = header.Value
				}

				log.Printf("\t\t%s: %s", header.Key, val)

				if strings.Contains(strings.ToLower(val), "malicious") || strings.Contains(strings.ToLower(header.Key), "malicious") {
					resp = &extProcPb.ProcessingResponse{
						Response: &extProcPb.ProcessingResponse_ImmediateResponse{
							ImmediateResponse: &extProcPb.ImmediateResponse{
								Status: &typev3.HttpStatus{
									Code: typev3.StatusCode_Forbidden,
								},
								Body: []byte("Blocked by AAPH Guardrail: Policy Violation."),
							},
						},
					}
					break
				}
			}

			log.Println("\n")

		case *extProcPb.ProcessingRequest_RequestBody:
			bodyStr := string(payload.RequestBody.Body)

			log.Println("\tRequest Body")
			log.Printf("\t\tBody String: %s", bodyStr)
			log.Printf("\t\tEnd of Stream: %v\n", payload.RequestBody.EndOfStream)

			if strings.Contains(strings.ToLower(bodyStr), "malicious") {
				log.Println("\t\tBlocked Malicious payload\n")

				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_ImmediateResponse{
						ImmediateResponse: &extProcPb.ImmediateResponse{
							Status: &typev3.HttpStatus{
								Code: typev3.StatusCode_Forbidden,
							},
							Body: []byte("Blocked by AAPH Guardrail: Policy Violation."),
						},
					},
				}
			} else {
				log.Println("\t\tApproved payload\n")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_RequestBody{
						RequestBody: &extProcPb.BodyResponse{},
					},
				}
			}

		case *extProcPb.ProcessingRequest_ResponseHeaders:
			log.Println("\tResponse Headers")

			resp = &extProcPb.ProcessingResponse{
				Response: &extProcPb.ProcessingResponse_ResponseHeaders{
					ResponseHeaders: &extProcPb.HeadersResponse{},
				},
			}

			for _, header := range payload.ResponseHeaders.Headers.Headers {
				val := string(header.RawValue)
				if val == "" {
					val = header.Value
				}

				log.Printf("\t\t%s: %s", header.Key, val)

				if strings.Contains(strings.ToLower(val), "malicious") || strings.Contains(strings.ToLower(header.Key), "malicious") {
					resp = &extProcPb.ProcessingResponse{
						Response: &extProcPb.ProcessingResponse_ImmediateResponse{
							ImmediateResponse: &extProcPb.ImmediateResponse{
								Status: &typev3.HttpStatus{
									Code: typev3.StatusCode_Forbidden,
								},
								Body: []byte("Blocked by AAPH Guardrail: Policy Violation."),
							},
						},
					}
					break
				}
			}

			log.Println("\n")

		case *extProcPb.ProcessingRequest_ResponseBody:
			bodyStr := string(payload.ResponseBody.Body)

			log.Println("\tResponse Body")
			log.Printf("\t\tBody String: %s", string(payload.ResponseBody.Body))
			log.Printf("\t\tEnd of Stream: %v\n", payload.ResponseBody.EndOfStream)

			if strings.Contains(strings.ToLower(bodyStr), "malicious") {
				log.Println("\t\tBlocked Malicious payload\n")

				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_ImmediateResponse{
						ImmediateResponse: &extProcPb.ImmediateResponse{
							Status: &typev3.HttpStatus{
								Code: typev3.StatusCode_Forbidden,
							},
							Body: []byte("Blocked by AAPH Guardrail: Policy Violation."),
						},
					},
				}
			} else {
				log.Println("\t\tApproved payload\n")
				resp = &extProcPb.ProcessingResponse{
					Response: &extProcPb.ProcessingResponse_ResponseBody{
						ResponseBody: &extProcPb.BodyResponse{},
					},
				}
			}

		default:
			log.Printf("\tUnknown Payload Type: %T", payload)

			resp = &extProcPb.ProcessingResponse{
				Response: &extProcPb.ProcessingResponse_RequestHeaders{
					RequestHeaders: &extProcPb.HeadersResponse{},
				},
			}
		}

		if err := stream.Send(resp); err != nil {
			log.Printf("Failed to send response back to Envoy: %v", err)
			return err
		}
	}
}

func main() {
	portFlag := flag.String("port", "9000", "Port to run the gRPC server on")
	flag.Parse()

	addr := fmt.Sprintf(":%s", strings.TrimPrefix(*portFlag, ":"))

	lis, err := net.Listen("tcp", addr)
	if err != nil {
		log.Fatalf("Failed to listen on %s: %v", addr, err)
	}

	grpcServer := grpc.NewServer()

	extProcPb.RegisterExternalProcessorServer(grpcServer, &extProcServer{})

	log.Printf("Starting ext_proc gRPC Server on port %s", addr)
	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("Failed to serve: %v", err)
	}
}
