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

// Result holds the verdict of an inspection.
type Result struct {
	IsBlocked bool
	Message   string
}

// Inspector defines how payloads should be evaluated.
type Inspector interface {
	// Inspect takes the payload type and its content, and returns a Result.
	Inspect(pType PayloadType, content string) Result
}
