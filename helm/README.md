# Agentic Protection — Helm Chart

Helm chart for the Agentic Protection demo stack: SSE, H2C, and H2CLL backend servers fronted by an Envoy AI Gateway with gRPC-based traffic inspection.

---

## Prerequisites

### 1. Envoy Gateway

Install [Envoy Gateway](https://gateway.envoyproxy.io/docs/tasks/quickstart/) into your cluster:

```bash
helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.8.2 -n envoy-gateway-system --create-namespace
```

Wait for the controller to be ready:

```bash
kubectl wait --timeout=5m -n envoy-gateway-system deployment/envoy-gateway --for=condition=Available
```

### 2. Envoy AI Gateway

Install [Envoy AI Gateway](https://aigateway.envoyproxy.io/docs/getting-started/installation):

```bash
helm upgrade -i aieg-crd oci://docker.io/envoyproxy/ai-gateway-crds-helm \
  --version v1.0.0 \
  --namespace envoy-ai-gateway-system \
  --create-namespace
```


```bash
helm upgrade -i aieg oci://docker.io/envoyproxy/ai-gateway-helm \
  --version v1.0.0 \
  --namespace envoy-ai-gateway-system \
  --create-namespace

kubectl wait --timeout=2m -n envoy-ai-gateway-system deployment/ai-gateway-controller --for=condition=Available
```

---

## Configuration

All configurable values are in [`values.yaml`](./values.yaml). Key parameters:

| Key | Default | Description |
|-----|---------|-------------|
| `namespace` | `llmg` | Kubernetes namespace for all resources |
| `gateway.hostname` | `pugr.serveirc.com` | Public hostname exposed by the Gateway |
| `gateway.tls.secretName` | `tls-secret` | Name of the TLS Secret referenced by the Gateway |
| `images.*` | see values.yaml | Container images for each component |

---

## Deployment

### Step 1: Set your hostname

Edit `values.yaml` and update the hostname:

```yaml
gateway:
  hostname: "your.domain.com"
```

To use a different namespace, update:

```yaml
namespace: your-namespace
```

### Step 2: Install the chart

```bash
helm install agentic-protection ./helm \
  --set gateway.hostname=your.domain.com \
  --set namespace=your-namespace
```

Or supply a custom values file:

```bash
helm install agentic-protection ./helm -f my-values.yaml
```

### Upgrade

```bash
helm upgrade agentic-protection ./helm -f my-values.yaml
```

### Uninstall

```bash
helm uninstall agentic-protection
kubectl delete namespace <namespace>
```

### Step 3: Provision TLS

Run the cert setup script from the `k8s-deployment/certs/` directory, passing your hostname and target namespace. The script generates a self-signed certificate and creates the TLS Secret in the cluster:

```bash
# From the repo root
cd k8s-deployment/certs

# Edit cert-setup.sh: replace the CN value with your hostname, namespace with target namespace, then run:
bash cert-setup.sh
```

The script runs:
```bash
openssl req -x509 -sha256 -nodes -days 365 -newkey rsa:2048 \
  -subj '/O=Your Org/CN=your.domain.com' \
  -keyout certs/cert.key -out certs/cert.crt

kubectl -n <namespace> create secret tls tls-secret --key=certs/cert.key --cert=certs/cert.crt
```

---

## Chart Structure

```
helm/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── namespace.yaml
    ├── gateway/
    │   ├── gateway-class.yaml
    │   ├── gateway.yaml
    │   ├── http-route.yaml
    │   └── network-policy.yaml
    ├── sse/
    │   ├── sse-safe-server.yaml
    │   └── sse-malicious-server.yaml
    ├── h2cll/
    │   ├── h2cll-safe-server.yaml
    │   └── h2cll-malicious-server.yaml
    ├── h2c/
    │   └── h2c-server.yaml
    ├── frontend/
    │   ├── frontend-configmap.yaml
    │   └── frontend-server.yaml
    └── grpc-inspection/
        ├── grpc-inspection-server.yaml
        └── grpc-inspection-envoy-policy.yaml
```
