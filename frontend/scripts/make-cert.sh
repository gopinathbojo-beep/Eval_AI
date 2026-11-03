#!/usr/bin/env bash
# Trusted local HTTPS, so phones on the same Wi-Fi can use the in-app camera (it needs HTTPS) without a
# "Not secure" warning. Makes a small local certificate authority (certs/eval-ai-local-ca.crt, kept and reused)
# and signs the dev server certificate (certs/cert.pem, certs/key.pem) with it.
# Trust the CA once per device: Windows -> scripts/trust-cert.ps1; phone -> install certs/eval-ai-local-ca.crt.
# Usage: bash scripts/make-cert.sh [lan-ip]   (default 192.168.1.11). vite.config.ts uses certs/ when both files exist.
set -euo pipefail
IP="${1:-192.168.1.11}"
cd "$(dirname "$0")/.."
mkdir -p certs
export MSYS_NO_PATHCONV=1
if [ ! -f certs/ca.key ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 3650 \
    -keyout certs/ca.key -out certs/eval-ai-local-ca.crt -subj "/CN=Eval AI Local CA" \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign"
fi
openssl req -newkey rsa:2048 -nodes -sha256 -keyout certs/key.pem -out certs/server.csr -subj "/CN=Eval AI local"
printf "subjectAltName=IP:%s,IP:127.0.0.1,DNS:localhost\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n" "$IP" > certs/server.ext
# 397 days: the longest validity browsers accept for a server certificate
openssl x509 -req -in certs/server.csr -CA certs/eval-ai-local-ca.crt -CAkey certs/ca.key -CAcreateserial \
  -days 397 -sha256 -extfile certs/server.ext -out certs/cert.pem
rm -f certs/server.csr certs/server.ext
echo "Wrote certs/cert.pem and certs/key.pem for ${IP}, 127.0.0.1 and localhost (signed by certs/eval-ai-local-ca.crt). Restart Vite."
