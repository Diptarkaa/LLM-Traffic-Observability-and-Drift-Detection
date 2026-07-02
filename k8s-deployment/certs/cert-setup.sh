openssl req -x509 -sha256 -nodes -days 365 -newkey rsa:2048 -subj '/O=Pugr Labs/CN=pugr.serveirc.com' -keyout certs/cert.key -out certs/cert.crt

kubectl -n llmg create secret tls tls-secret --key=certs/cert.key --cert=certs/cert.crt
