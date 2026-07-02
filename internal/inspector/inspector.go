// Package inspector defines the interfaces and logic for inspecting traffic payloads.
package inspector

// PayloadType represents the part of the HTTP lifecycle being inspected.
type PayloadType int

const (
	RequestHeader PayloadType = iota
	RequestBody
	ResponseHeader
	ResponseBody
)

// Result represents the action Envoy should take based on the inspection.
type Result int

const (
	Safe Result = iota
	Warn
	Block
)

// StreamContext holds the aggregated payload data for a single Envoy stream lifecycle.
type StreamContext struct {
	RequestHeaders  map[string]string
	RequestBody     string
	ResponseHeaders map[string]string
	ResponseBody    string
}

// Inspector defines how payloads should be evaluated.
type Inspector interface {
	// Inspect takes the payload type and its content, and returns a Result.
	Inspect(pType PayloadType, content string, streamContext *StreamContext) Result
}
