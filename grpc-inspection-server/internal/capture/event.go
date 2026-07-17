package capture

import "time"

// Event is a raw ext_proc frame envelope emitted to Kafka.
type Event struct {
	EventID     string            `json:"event_id"`
	Source      string            `json:"source"`
	Timestamp   time.Time         `json:"timestamp"`
	StreamID    string            `json:"stream_id"`
	RequestID   string            `json:"request_id,omitempty"`
	FrameType   string            `json:"frame_type"`
	FrameSeq    uint64            `json:"frame_seq"`
	EndOfStream bool              `json:"end_of_stream"`
	Headers     map[string]string `json:"headers,omitempty"`
	Body        string            `json:"body,omitempty"`
	BodySize    int               `json:"body_size"`
	Decision    string            `json:"decision"`
	Blocked     bool              `json:"blocked"`
	Warned      bool              `json:"warned"`
}
