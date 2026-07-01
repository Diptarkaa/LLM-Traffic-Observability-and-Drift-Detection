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

// ResultType represents the action Envoy should take based on the inspection.
type ResultType int

const (
	Safe ResultType = iota
	Warn
	Block
)

// Result holds the verdict of an inspection.
type Result struct {
	Type    ResultType
	Body    string
	Headers []string
}

// Inspector defines how payloads should be evaluated.
type Inspector interface {
	// Inspect takes the payload type and its content, and returns a Result.
	Inspect(pType PayloadType, content string) Result
}
