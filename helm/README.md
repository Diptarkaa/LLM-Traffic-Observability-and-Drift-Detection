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
| `createNamespace` | `false` | Create the Namespace resource from the chart; set to `true` if not using `--create-namespace` |
| `nameOverride` | `""` | Override the chart name component of resource names |
| `fullnameOverride` | `""` | Override the full resource name prefix entirely |
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

### Step 2: Install the chart

The chart uses `.Release.Namespace` for all resource namespaces, pass the target namespace via the standard Helm flag. Use `--create-namespace` to have Helm create it automatically, or set `createNamespace: true` in `values.yaml` to let the chart manage the Namespace resource itself.

```bash
helm install agentic-protection ./helm \
  --namespace llmg \
  --create-namespace \
  --set gateway.hostname=your.domain.com
```

Or supply a custom values file:

```bash
helm install agentic-protection ./helm \
  --namespace llmg \
  --create-namespace \
  -f my-values.yaml
```

To run a second environment alongside an existing installation, use a different release name:

```bash
helm install staging ./helm \
  --namespace llmg \
  --set gateway.hostname=staging.domain.com
```

### Upgrade

```bash
helm upgrade agentic-protection ./helm --namespace llmg -f my-values.yaml
```

### Uninstall

```bash
helm uninstall agentic-protection --namespace llmg
kubectl delete namespace llmg
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
    ├── _helpers.tpl
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
