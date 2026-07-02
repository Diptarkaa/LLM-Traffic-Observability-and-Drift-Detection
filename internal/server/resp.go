package server

import (
	"github.com/AkamaiAAPH/agentic-protection/internal/inspector"

	corev3 "github.com/envoyproxy/go-control-plane/envoy/config/core/v3"
	extProcPb "github.com/envoyproxy/go-control-plane/envoy/service/ext_proc/v3"
	typev3 "github.com/envoyproxy/go-control-plane/envoy/type/v3"
)

// helper to parse map[string]string into Envoy HeaderMutations
func buildHeaderMutations(headers map[string]string) *extProcPb.HeaderMutation {
	if len(headers) == 0 {
		return nil
	}

	var setHeaders []*corev3.HeaderValueOption
	for key, val := range headers {
		setHeaders = append(setHeaders, &corev3.HeaderValueOption{
			Header: &corev3.HeaderValue{
				Key:      key,
				Value:    val,
				RawValue: []byte(val),
			},
			AppendAction: corev3.HeaderValueOption_OVERWRITE_IF_EXISTS_OR_ADD,
		})
	}

	return &extProcPb.HeaderMutation{
		SetHeaders: setHeaders,
	}
}

// buildResponse constructs the Envoy response using values from the StreamContext
func buildResponse(pType inspector.PayloadType, result inspector.Result, ctx *inspector.StreamContext) *extProcPb.ProcessingResponse {
	// Handle Block with ImmediateResponse (403 Forbidden)
	if result == inspector.Block {
		return &extProcPb.ProcessingResponse{
			Response: &extProcPb.ProcessingResponse_ImmediateResponse{
				ImmediateResponse: &extProcPb.ImmediateResponse{
					Status: &typev3.HttpStatus{
						Code: typev3.StatusCode_Forbidden,
					},
					Headers: buildHeaderMutations(ctx.ResponseHeaders),
					Body:    []byte(ctx.ResponseBody),
				},
			},
		}
	}

	// Handle Safe/Warn (Allow traffic, mutate if context fields are populated)
	switch pType {
	case inspector.RequestHeader:
		return &extProcPb.ProcessingResponse{
			Response: &extProcPb.ProcessingResponse_RequestHeaders{
				RequestHeaders: &extProcPb.HeadersResponse{
					Response: &extProcPb.CommonResponse{
						HeaderMutation: buildHeaderMutations(ctx.RequestHeaders),
					},
				},
			},
		}

	case inspector.RequestBody:
		resp := &extProcPb.ProcessingResponse_RequestBody{
			RequestBody: &extProcPb.BodyResponse{},
		}
		if ctx.RequestBody != "" {
			resp.RequestBody.Response = &extProcPb.CommonResponse{
				BodyMutation: &extProcPb.BodyMutation{
					Mutation: &extProcPb.BodyMutation_Body{
						Body: []byte(ctx.RequestBody),
					},
				},
			}
		}
		return &extProcPb.ProcessingResponse{Response: resp}

	case inspector.ResponseHeader:
		return &extProcPb.ProcessingResponse{
			Response: &extProcPb.ProcessingResponse_ResponseHeaders{
				ResponseHeaders: &extProcPb.HeadersResponse{
					Response: &extProcPb.CommonResponse{
						HeaderMutation: buildHeaderMutations(ctx.ResponseHeaders),
					},
				},
			},
		}

	case inspector.ResponseBody:
		resp := &extProcPb.ProcessingResponse_ResponseBody{
			ResponseBody: &extProcPb.BodyResponse{},
		}
		if ctx.ResponseBody != "" {
			resp.ResponseBody.Response = &extProcPb.CommonResponse{
				BodyMutation: &extProcPb.BodyMutation{
					Mutation: &extProcPb.BodyMutation_Body{
						Body: []byte(ctx.ResponseBody),
					},
				},
			}
		}
		return &extProcPb.ProcessingResponse{Response: resp}
	}

	// Fallback
	return &extProcPb.ProcessingResponse{}
}
