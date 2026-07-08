cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: openrouter-apikey
  namespace: llmg
type: Opaque
stringData:
  apiKey: ${OPENROUTER_API_KEY}
EOF
