package capture

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"sync"
	"time"
)

// HTTPBridgeConfig controls async delivery from extproc to a bridge endpoint.
type HTTPBridgeConfig struct {
	EndpointURL string
	QueueSize   int
	Timeout     time.Duration
}

// HTTPBridgeEmitter asynchronously POSTs events to a bridge service.
type HTTPBridgeEmitter struct {
	endpointURL string
	httpClient  *http.Client
	queue       chan Event

	wg   sync.WaitGroup
	once sync.Once
}

func NewHTTPBridgeEmitter(cfg HTTPBridgeConfig) (*HTTPBridgeEmitter, error) {
	if cfg.EndpointURL == "" {
		return nil, errors.New("bridge endpoint URL is required")
	}
	if cfg.QueueSize <= 0 {
		cfg.QueueSize = 2048
	}
	if cfg.Timeout <= 0 {
		cfg.Timeout = 500 * time.Millisecond
	}

	e := &HTTPBridgeEmitter{
		endpointURL: cfg.EndpointURL,
		httpClient: &http.Client{
			Timeout: cfg.Timeout,
		},
		queue: make(chan Event, cfg.QueueSize),
	}

	e.wg.Add(1)
	go e.run()

	return e, nil
}

func (e *HTTPBridgeEmitter) run() {
	defer e.wg.Done()

	for event := range e.queue {
		payload, err := json.Marshal(event)
		if err != nil {
			continue
		}

		req, err := http.NewRequest(http.MethodPost, e.endpointURL, bytes.NewReader(payload))
		if err != nil {
			continue
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := e.httpClient.Do(req)
		if err != nil {
			continue
		}

		_ = resp.Body.Close()
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			continue
		}
	}
}

func (e *HTTPBridgeEmitter) Emit(event Event) error {
	select {
	case e.queue <- event:
		return nil
	default:
		return ErrQueueFull
	}
}

func (e *HTTPBridgeEmitter) Close(ctx context.Context) error {
	var closeErr error
	e.once.Do(func() {
		close(e.queue)

		done := make(chan struct{})
		go func() {
			e.wg.Wait()
			close(done)
		}()

		select {
		case <-done:
		case <-ctx.Done():
			closeErr = fmt.Errorf("bridge emitter close timeout: %w", ctx.Err())
		}
	})

	return closeErr
}
