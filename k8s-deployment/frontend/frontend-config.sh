kubectl -n llmg create configmap frontend-html \
  --from-file=index.html=frontend/index.html \
  --from-file=llm.html=frontend/llm.html
