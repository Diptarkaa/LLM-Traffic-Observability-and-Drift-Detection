package main

import (
	"flag"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"strings"
	"time"

	"golang.org/x/net/http2"
	"golang.org/x/net/http2/h2c"
)

func generateJunkData(length int) string {
	const charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*() "
	b := make([]byte, length)
	for i := range b {
		b[i] = charset[rand.Intn(len(charset))]
	}
	return string(b)
}

func main() {
	port := flag.String("port", "8000", "Port to run the h2c server on")
	interval := flag.Duration("interval", 1*time.Second, "Time interval between pushed chunks")
	malicious := flag.Bool("malicious", false, "Inject the 'malicious-server' string once per stream")
	flag.Parse()

	rand.Seed(time.Now().UnixNano())

	mux := http.NewServeMux()

	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		clientAddr := r.RemoteAddr
		log.Printf("[START] Connection established from %s using %s", clientAddr, r.Proto)

		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "Streaming not supported", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "text/plain")
		w.WriteHeader(http.StatusOK)
		flusher.Flush()

		log.Printf("[FLUSH] Initial HTTP headers sent to %s", clientAddr)

		ticker := time.NewTicker(*interval)
		defer ticker.Stop()

		i := 1
		maliciousInjected := false

		for {
			select {
			case <-r.Context().Done():
				log.Printf("[END] Connection ended by client %s", clientAddr)
				return
			case <-ticker.C:
				var payload string

				if *malicious && !maliciousInjected && (rand.Float32() < 0.25 || i == 5) {
					payload = "malicious-server"
					maliciousInjected = true
					log.Printf("[WARNING] Injected malicious payload to %s", clientAddr)
				} else {
					junkLength := rand.Intn(51) + 10
					payload = generateJunkData(junkLength)
				}

				msg := fmt.Sprintf("Message %d | Time: %s | Payload: %s\n",
					i, time.Now().Format("15:04:05"), payload)

				if _, err := fmt.Fprint(w, msg); err != nil {
					log.Printf("[END] Write failed to %s: %v", clientAddr, err)
					return
				}
				flusher.Flush()

				cleanMsg := strings.TrimSpace(msg)
				log.Printf("[FLUSH] Data pushed (%d bytes total) -> %s", len(msg), cleanMsg)
				i++
			}
		}
	})

	h2s := &http2.Server{}
	server := &http.Server{
		Addr:    ":" + *port,
		Handler: h2c.NewHandler(mux, h2s),
	}

	log.Printf("Starting h2c long lived server on port %s | Interval: %v | Malicious Mode: %v", *port, *interval, *malicious)
	if err := server.ListenAndServe(); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
