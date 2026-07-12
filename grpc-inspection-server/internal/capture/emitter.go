package capture

import (
	"context"
	"errors"
)

var (
	ErrQueueFull = errors.New("capture queue full")
)

// Emitter sends events to an external sink. Implementations must be fail-open at callsites.
type Emitter interface {
	Emit(event Event) error
	Close(ctx context.Context) error
}

type noopEmitter struct{}

// NewNoopEmitter returns an emitter that drops every event.
func NewNoopEmitter() Emitter {
	return &noopEmitter{}
}

func (n *noopEmitter) Emit(event Event) error {
	return nil
}

func (n *noopEmitter) Close(ctx context.Context) error {
	return nil
}
