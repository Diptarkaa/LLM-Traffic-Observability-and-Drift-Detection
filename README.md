# gRPC Inspection Server for Envoy
This is a simple gRPC server that implements Envoy's External Processing (`ext_proc`) API. It acts as an external processing/inspection service for Envoy.
It streams HTTP request and response parts (headers and bodies) from Envoy, inspects them, and immediately blocks the traffic with a 403 Forbidden status if found malicious.

## Features
- Inspects Request Headers and Body
- Inspects Response Headers and Body
- Blocks traffic immediately if found malicious.
