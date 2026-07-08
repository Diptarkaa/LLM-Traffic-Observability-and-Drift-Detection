// Package encoding provides helpers for compressing and decompressing payloads.
package encoding

import (
	"compress/gzip"
	"fmt"
	"io"
	"strings"
)

// Decompressor handles streaming decompression of payloads.
type Decompressor struct {
	encoding string
	pw       *io.PipeWriter
	outChan  chan []byte
	errChan  chan error
	started  bool
}

// New creates a new Decompressor for the specified encoding type.
func New(encoding string) *Decompressor {
	return &Decompressor{
		encoding: strings.ToLower(strings.TrimSpace(encoding)),
		outChan:  make(chan []byte, 100),
		errChan:  make(chan error, 1),
	}
}

// init starts the background decompression goroutine for supported encodings.
func (d *Decompressor) init() {
	d.started = true

	if d.encoding != "gzip" {
		return
	}

	pr, pw := io.Pipe()
	d.pw = pw

	go func() {
		zr, err := gzip.NewReader(pr)
		if err != nil {
			d.errChan <- err
			return
		}
		defer zr.Close()

		buf := make([]byte, 8192)
		for {
			n, err := zr.Read(buf)
			if n > 0 {
				chunk := make([]byte, n)
				copy(chunk, buf[:n])
				d.outChan <- chunk
			}
			if err != nil {
				d.errChan <- err
				return
			}
		}
	}()
}

// Decompress decompresses chunks of supported encoding
func (d *Decompressor) Decompress(data []byte, endOfStream bool) ([]byte, error) {
	if d.encoding != "gzip" {
		return data, nil
	}

	if !d.started {
		d.init()
	}

	if len(data) > 0 {
		if _, err := d.pw.Write(data); err != nil {
			return nil, fmt.Errorf("failed to write to %s pipe: %w", d.encoding, err)
		}
	}

	if endOfStream {
		if d.pw != nil {
			d.pw.Close()
		}
	}

	var decompressed []byte

	if endOfStream {
	drainLoop:
		for {
			select {
			case chunk := <-d.outChan:
				decompressed = append(decompressed, chunk...)
			case err := <-d.errChan:
				if err != nil && err != io.EOF {
					return decompressed, err
				}
				break drainLoop
			}
		}
	} else {
	readLoop:
		for {
			select {
			case chunk := <-d.outChan:
				decompressed = append(decompressed, chunk...)
			case err := <-d.errChan:
				if err != nil && err != io.EOF {
					return decompressed, err
				}
				break readLoop
			default:
				break readLoop
			}
		}
	}

	return decompressed, nil
}

// Close ensures the pipe writer is closed, stopping the background goroutine.
func (d *Decompressor) Close() {
	if d.pw != nil {
		d.pw.Close()
	}
}
